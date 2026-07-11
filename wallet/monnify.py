import logging
from decimal import Decimal

import requests
import base64
from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class MonnifyError(Exception):
    pass


class MonnifyService:
    BASE_URL = "https://api.monnify.com/api/v1"
    TIMEOUT = 30

    @classmethod
    def _get_headers(cls):
        auth_str = f"{settings.MONNIFY_API_KEY}:{settings.MONNIFY_SECRET_KEY}"
        encoded = base64.b64encode(auth_str.encode()).decode()
        resp = requests.post(
            f"{cls.BASE_URL}/auth/login",
            headers={"Authorization": f"Basic {encoded}"},
            timeout=cls.TIMEOUT,
        )
        if resp.status_code != 200:
            logger.error("Monnify auth failed: status=%s body=%s", resp.status_code, resp.text)
            raise MonnifyError(f"Monnify authentication failed (HTTP {resp.status_code})")
        data = resp.json()
        token = data.get("responseBody", {}).get("accessToken")
        if not token:
            logger.error("Monnify auth response missing accessToken: %s", data)
            raise MonnifyError("Monnify authentication returned no access token")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @classmethod
    def create_reserved_account(cls, user, bvn=None, nin=None):
        if not bvn and not nin:
            raise MonnifyError("Either bvn or nin is required to create a reserved account")

        headers = cls._get_headers()
        url = "https://api.monnify.com/api/v2/bank-transfer/reserved-accounts"

        account_name = f"{user.first_name} {user.last_name}".strip()
        if not account_name:
            account_name = user.username

        payload = {
            "accountReference": f"TIC-{user.id}",
            "accountName": account_name,
            "currencyCode": "NGN",
            "contractCode": settings.MONNIFY_CONTRACT_CODE,
            "customerEmail": user.email,
            "customerName": account_name,
            "getAllAvailableBanks": True,
        }
        if bvn:
            payload["bvn"] = bvn
        if nin:
            payload["nin"] = nin

        resp = requests.post(url, json=payload, headers=headers, timeout=cls.TIMEOUT)
        body = resp.json()

        if resp.status_code != 200:
            logger.error(
                "Monnify account creation failed: status=%s body=%s",
                resp.status_code,
                body,
            )
            msg = body.get("responseMessage", body.get("message", "Monnify request failed"))
            raise MonnifyError(msg)

        if not body.get("requestSuccessful"):
            logger.error("Monnify rejected request: %s", body)
            msg = body.get("responseMessage", body.get("message", "Monnify rejected the request"))
            raise MonnifyError(msg)

        response_body = body.get("responseBody", {})
        accounts = response_body.get("accounts", [])

        if not accounts:
            logger.error("Monnify returned no accounts in response: %s", body)
            msg = body.get("responseMessage", "Monnify returned no bank accounts")
            raise MonnifyError(msg)

        first = accounts[0]
        return {
            "bank_name": first.get("bankName", "Unknown"),
            "account_number": first.get("accountNumber", ""),
            "account_reference": response_body.get("accountReference", ""),
            "account_name": response_body.get("accountName", account_name),
        }

    @classmethod
    def get_reserved_account_transactions(cls, account_reference, page=0, size=20):
        """
        Fetch recent transactions for a reserved account, for reconciliation of
        deposits whose webhook never arrived.

        NOTE: implemented from Monnify's documented reserved-account transactions
        endpoint from memory (no live docs access at write time) — the parsing
        below is deliberately defensive (tries multiple known field-name variants,
        same pattern already used in the webhook handler) to reduce breakage if a
        field name is slightly off. Verify against a real sandbox response before
        relying on this in production.
        """
        headers = cls._get_headers()
        url = f"{cls.BASE_URL}/bank-transfer/reserved-accounts/transactions"
        params = {"accountReference": account_reference, "page": page, "size": size}

        resp = requests.get(url, headers=headers, params=params, timeout=cls.TIMEOUT)
        body = resp.json()

        if resp.status_code != 200 or not body.get("requestSuccessful"):
            msg = body.get("responseMessage", body.get("message", "Monnify request failed"))
            raise MonnifyError(msg)

        response_body = body.get("responseBody", {})
        content = response_body.get("content", response_body if isinstance(response_body, list) else [])

        transactions = []
        for item in content:
            status = (item.get("paymentStatus") or item.get("transactionStatus") or item.get("status") or "").upper()
            transactions.append({
                "amount_paid": Decimal(str(item.get("amountPaid") or item.get("amount") or "0")),
                "transaction_reference": str(item.get("transactionReference") or item.get("paymentReference") or ""),
                "status": status,
                "raw": item,
            })
        return transactions

    @classmethod
    def credit_deposit(cls, wallet, amount_paid, txn_ref):
        """
        Idempotently credit a wallet for a successful reserved-account deposit.
        Shared by the webhook handler and the reconciliation sweep so both apply
        the exact same fee/crediting logic. Returns True if credited, False if
        this reference was already processed.
        """
        from .models import Transaction, Wallet

        if txn_ref and Transaction.objects.filter(reference=txn_ref).exists():
            return False

        with db_transaction.atomic():
            locked = Wallet.objects.select_for_update().get(pk=wallet.pk)

            fee = Decimal("50.00")
            net_credit = max(amount_paid - fee, Decimal("0.00"))

            locked.balance += net_credit
            locked.save(update_fields=["balance"])

            Transaction.objects.create(
                user=locked.user,
                trans_type="DEPOSIT",
                amount=amount_paid,
                fee=fee,
                net_amount=net_credit,
                status="SUCCESSFUL",
                reference=txn_ref or f"WEBHOOK-{wallet.user_id}-{timezone.now().strftime('%Y%m%d%H%M%S%f')}",
            )
        return True
