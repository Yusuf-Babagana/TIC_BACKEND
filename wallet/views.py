import hashlib
import hmac
import json
import logging
import re
import traceback
from decimal import Decimal

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, status
from rest_framework.parsers import BaseParser

logger = logging.getLogger(__name__)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Wallet, Transaction
from .monnify import MonnifyService, MonnifyError
from .serializers import TransactionSerializer


class WalletBalanceView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = request.user.wallet
        return Response({
            "balance": str(wallet.balance),
            "bank_name": wallet.bank_name,
            "account_number": wallet.account_number,
            "account_name": wallet.account_name or f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
        }, status=200)


class RawJsonPassthroughParser(BaseParser):
    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read()


@method_decorator(csrf_exempt, name="dispatch")
class MonnifyWebhookView(APIView):
    parser_classes = [RawJsonPassthroughParser]
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        from dashboard.utils import client_ip, log_webhook_event

        raw_body = request.data
        ip = client_ip(request)

        # 0. Verify the request actually came from Monnify (HMAC-SHA512 of the raw
        # body, keyed with the client secret) before trusting anything in it —
        # without this check, anyone can POST a fake payload and credit any wallet.
        signature = request.headers.get("monnify-signature", "")
        expected = hmac.new(
            settings.MONNIFY_SECRET_KEY.encode(), raw_body, hashlib.sha512
        ).hexdigest()
        if not signature or not hmac.compare_digest(signature, expected):
            logger.warning("Monnify webhook rejected: missing/invalid signature")
            log_webhook_event(
                "monnify", "signature_rejected",
                detail="Missing or invalid monnify-signature header",
                payload=raw_body.decode("utf-8", errors="replace")[:1000],
                ip_address=ip,
            )
            return Response({"error": "Invalid signature"}, status=401)

        # 1. Parse payload
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            logger.error("Monnify webhook JSON parse error: %s", e)
            log_webhook_event(
                "monnify", "invalid_payload", detail=str(e),
                payload=raw_body.decode("utf-8", errors="replace")[:1000],
                ip_address=ip,
            )
            return Response({"error": "Invalid JSON"}, status=400)

        # 2. Extract event data
        event_type = payload.get("eventType", "")
        event_data = payload.get("eventData", {})
        logger.info("Monnify webhook eventType=%s", event_type)

        amount_paid = Decimal(str(event_data.get("amountPaid", "0")))

        # Try BOTH flat AND nested accountNumber paths
        account_number = (
            event_data.get("destinationAccountNumber")
            or (event_data.get("destinationAccountInformation") or {}).get("accountNumber")
        )

        txn_ref_raw = event_data.get("transactionReference")
        txn_ref = str(txn_ref_raw) if txn_ref_raw else ""
        account_ref_raw = event_data.get("destinationAccountReference") or event_data.get("paymentReference")
        account_ref = str(account_ref_raw) if account_ref_raw else ""

        logger.info(
            "Monnify webhook amount=%s account=%s txn_ref=%s account_ref=%s",
            amount_paid, account_number, txn_ref, account_ref,
        )
        webhook_detail = f"amount={amount_paid} account={account_number} txn_ref={txn_ref} account_ref={account_ref}"

        from wallet.models import Wallet, Transaction

        # ──────────────────────────────────────────────
        # STRATEGY 1: User ID from transactionReference (format: MNFY|16|...)
        # ──────────────────────────────────────────────
        wallet = None
        user_id_from_ref = None
        parts = txn_ref.split("|")
        if len(parts) >= 2 and parts[1].isdigit():
            user_id_from_ref = int(parts[1])
            wallet = Wallet.objects.filter(user_id=user_id_from_ref).first()
            if wallet:
                logger.info("Monnify webhook strategy 1 hit: user_id=%s account=%s", user_id_from_ref, wallet.account_number)
            else:
                logger.info("Monnify webhook strategy 1 miss: no wallet for user_id=%s", user_id_from_ref)

        # ──────────────────────────────────────────────
        # STRATEGY 2: Account Number from payload
        # ──────────────────────────────────────────────
        if not wallet and account_number:
            wallet = Wallet.objects.filter(account_number=account_number).first()
            if wallet:
                logger.info("Monnify webhook strategy 2 hit: account=%s user_id=%s", account_number, wallet.user_id)
            else:
                logger.info("Monnify webhook strategy 2 miss: no wallet for account=%s", account_number)

        # ──────────────────────────────────────────────
        # STRATEGY 3: Digits from account_ref (legacy ABDTIC-16)
        # ──────────────────────────────────────────────
        if not wallet and account_ref:
            digit_match = re.findall(r"\d+", account_ref)
            if digit_match:
                wallet = Wallet.objects.filter(user_id=int(digit_match[0])).first()
                if wallet:
                    logger.info("Monnify webhook strategy 3 hit: ref_digits=%s account=%s", digit_match[0], wallet.account_number)
                else:
                    logger.info("Monnify webhook strategy 3 miss: no wallet for ref_digits=%s", digit_match[0])

        if not wallet:
            logger.warning("Monnify webhook: wallet not found via any strategy")
            log_webhook_event(
                "monnify", "wallet_not_found", detail=webhook_detail,
                payload=json.dumps(event_data)[:1000], ip_address=ip, event_type=event_type,
            )
            return Response({"error": "Wallet not found"}, status=404)

        # ──────────────────────────────────────────────
        # CREDIT (idempotent — shared with the reconciliation sweep)
        # ──────────────────────────────────────────────
        try:
            credited = MonnifyService.credit_deposit(wallet, amount_paid, txn_ref)
        except Exception as e:
            logger.error("Monnify webhook credit error: %s", e)
            log_webhook_event(
                "monnify", "error", detail=f"{webhook_detail} error={e}",
                payload=json.dumps(event_data)[:1000], ip_address=ip, event_type=event_type,
            )
            return Response({"error": str(e)}, status=500)

        if not credited:
            logger.info("Monnify webhook duplicate: %s already processed", txn_ref)
            log_webhook_event(
                "monnify", "duplicate_ignored", detail=webhook_detail,
                payload=json.dumps(event_data)[:1000], ip_address=ip, event_type=event_type,
            )
            return Response({"status": "ignored"}, status=200)

        logger.info("Monnify webhook success: user_id=%s ref=%s", wallet.user_id, txn_ref)
        log_webhook_event(
            "monnify", "credited", detail=f"user_id={wallet.user_id} {webhook_detail}",
            payload=json.dumps(event_data)[:1000], ip_address=ip, event_type=event_type,
        )
        return Response({"status": "success"}, status=200)


class TransactionHistoryView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user).order_by(
            "-created_at"
        )


class SubmitBVNView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.info(
            "SubmitBVNView hit by user id=%s username=%s email=%s",
            request.user.id,
            request.user.username,
            request.user.email,
        )

        if request.user.wallet.account_number:
            return Response(
                {"error": "Account already exists"}, status=status.HTTP_400_BAD_REQUEST
            )

        bvn = (request.data.get("bvn") or "").strip()
        nin = (request.data.get("nin") or "").strip()

        if settings.DEBUG and not bvn and not nin:
            bvn = "22241354089"

        if not bvn and not nin:
            return Response(
                {"error": "bvn or nin is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        if bvn and not re.fullmatch(r"\d{11}", bvn):
            return Response(
                {"error": "BVN must be exactly 11 digits"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if nin and not re.fullmatch(r"\d{11}", nin):
            return Response(
                {"error": "NIN must be exactly 11 digits"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        wallet = request.user.wallet

        try:
            account = MonnifyService.create_reserved_account(
                request.user, bvn=bvn or None, nin=nin or None
            )
            wallet.bank_name = account["bank_name"]
            wallet.account_number = account["account_number"]
            wallet.account_reference = account["account_reference"]
            wallet.account_name = account["account_name"]
            wallet.save(update_fields=["bank_name", "account_number", "account_reference", "account_name"])

            response_data = {
                "bank_name": account["bank_name"],
                "account_number": account["account_number"],
                "account_reference": account["account_reference"],
                "account_name": account["account_name"],
            }

            return Response(
                {
                    "message": "Account generated successfully",
                    "data": response_data,
                },
                status=status.HTTP_200_OK,
            )

        except MonnifyError as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error("BVN Submission Crash: %s", str(e))
            logger.error(traceback.format_exc())
            return Response(
                {
                    "status": "error",
                    "message": "Failed to connect to identity provider",
                    "details": str(e),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
