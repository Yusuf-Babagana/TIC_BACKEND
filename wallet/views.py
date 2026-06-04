import hashlib
import hmac
import json
import logging
import re
import traceback
from decimal import Decimal

from django.conf import settings
from django.db import transaction
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
            "account_name": wallet.account_name,
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
        raw_body = request.data

        # 1. Parse payload
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            print(f"DEBUG: JSON PARSE ERROR: {str(e)}")
            return Response({"error": "Invalid JSON"}, status=400)

        # 2. Extract event data
        event_type = payload.get("eventType", "")
        event_data = payload.get("eventData", {})
        print(f"DEBUG: eventType={event_type}")

        amount_paid = Decimal(str(event_data.get("amountPaid", "0")))

        # ⚡ Try BOTH flat AND nested accountNumber paths
        account_number = (
            event_data.get("destinationAccountNumber")
            or (event_data.get("destinationAccountInformation") or {}).get("accountNumber")
        )

        txn_ref_raw = event_data.get("transactionReference")
        txn_ref = str(txn_ref_raw) if txn_ref_raw else ""
        account_ref_raw = event_data.get("destinationAccountReference") or event_data.get("paymentReference")
        account_ref = str(account_ref_raw) if account_ref_raw else ""

        print(f"DEBUG: amount={amount_paid} account={account_number} txn_ref={txn_ref} account_ref={account_ref}")

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
                print(f"DEBUG: STRATEGY 1 HIT — user_id={user_id_from_ref} account={wallet.account_number}")
            else:
                print(f"DEBUG: STRATEGY 1 MISS — no wallet for user_id={user_id_from_ref}")

        # ──────────────────────────────────────────────
        # STRATEGY 2: Account Number from payload
        # ──────────────────────────────────────────────
        if not wallet and account_number:
            wallet = Wallet.objects.filter(account_number=account_number).first()
            if wallet:
                print(f"DEBUG: STRATEGY 2 HIT — account={account_number} user_id={wallet.user_id}")
            else:
                print(f"DEBUG: STRATEGY 2 MISS — no wallet for account={account_number}")

        # ──────────────────────────────────────────────
        # STRATEGY 3: Digits from account_ref (legacy ABDTIC-16)
        # ──────────────────────────────────────────────
        if not wallet and account_ref:
            digit_match = re.findall(r"\d+", account_ref)
            if digit_match:
                wallet = Wallet.objects.filter(user_id=int(digit_match[0])).first()
                if wallet:
                    print(f"DEBUG: STRATEGY 3 HIT — ref_digits={digit_match[0]} account={wallet.account_number}")
                else:
                    print(f"DEBUG: STRATEGY 3 MISS — no wallet for ref_digits={digit_match[0]}")

        if not wallet:
            print("DEBUG: CRITICAL — wallet not found via any strategy")
            return Response({"error": "Wallet not found"}, status=404)

        # ──────────────────────────────────────────────
        # IDEMPOTENCY CHECK
        # ──────────────────────────────────────────────
        if txn_ref:
            if Transaction.objects.filter(reference=txn_ref).exists():
                print(f"DEBUG: Duplicate — {txn_ref} already processed")
                return Response({"status": "ignored"}, status=200)

        # ──────────────────────────────────────────────
        # ATOMIC CREDIT + FEE DEDUCTION
        # ──────────────────────────────────────────────
        try:
            with transaction.atomic():
                locked = Wallet.objects.select_for_update().get(pk=wallet.pk)

                FEE = Decimal("50.00")
                net_credit = max(amount_paid - FEE, Decimal("0.00"))

                locked.balance += net_credit
                locked.save()

                Transaction.objects.create(
                    user=locked.user,
                    trans_type="DEPOSIT",
                    amount=amount_paid,
                    fee=FEE,
                    net_amount=net_credit,
                    status="SUCCESSFUL",
                    reference=txn_ref or f"WEBHOOK-{wallet.user_id}",
                )

            print(f"DEBUG: SUCCESS — User {locked.user_id} ({locked.user.username}) credited ₦{net_credit}")
            return Response({"status": "success"}, status=200)

        except Exception as e:
            print(f"DEBUG: ATOMIC CREDIT ERROR: {str(e)}")
            return Response({"error": str(e)}, status=500)


class TransactionHistoryView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user).order_by(
            "-created_at"
        )


class GenerateAccountView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        wallet = request.user.wallet
        if wallet.account_number:
            return Response(
                {"message": "Account already exists"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            account = MonnifyService.create_reserved_account(request.user)
            wallet.bank_name = account["bank_name"]
            wallet.account_number = account["account_number"]
            wallet.account_reference = account["account_reference"]
            wallet.account_name = account["account_name"]
            wallet.save()
            return Response(
                {"message": "Account generated successfully", "data": account},
                status=status.HTTP_200_OK,
            )
        except MonnifyError as e:
            return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("GenerateAccount Crash: %s", str(e))
            logger.error(traceback.format_exc())
            return Response(
                {
                    "status": "error",
                    "message": "Failed to connect to identity provider",
                    "details": str(e),
                },
                status=status.HTTP_502_BAD_GATEWAY,
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

        bvn = request.data.get("bvn")
        nin = request.data.get("nin")

        if settings.DEBUG:
            if not bvn or bvn in ["", "string", "00000000000"]:
                bvn = "22241354089"
            if not nin or nin in ["", "string"]:
                nin = "72533591954"

        bvn = (bvn or "").strip()
        nin = (nin or "").strip()

        if not re.fullmatch(r"\d{11}", bvn):
            return Response(
                {"error": "BVN must be exactly 11 digits"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        wallet = request.user.wallet

        try:
            account = MonnifyService.create_reserved_account(
                request.user, bvn=bvn
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
