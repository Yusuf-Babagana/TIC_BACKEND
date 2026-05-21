import logging

import requests
import base64
from django.conf import settings

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
    def create_reserved_account(cls, user, bvn=None):
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
            "bvn": bvn or settings.PROXY_TEST_BVN,
            "getAllAvailableBanks": True,
        }

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
        }
