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
        }, status=200)


class RawJsonPassthroughParser(BaseParser):
    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read()


@method_decorator(csrf_exempt, name="dispatch")
class MonnifyWebhookView(APIView):
    permission_classes = []
    authentication_classes = []
    parser_classes = [RawJsonPassthroughParser]

    def post(self, request, *args, **kwargs):
        raw_body = request.data

        # ──────────────────────────────────────────────
        # 1. TRACE INPUT
        # ──────────────────────────────────────────────
        print(f"DEBUG_TRACE: Received Request Length: {len(raw_body)} bytes")

        # ──────────────────────────────────────────────
        # 2. SIGNATURE VERIFICATION
        # ──────────────────────────────────────────────
        monnify_signature = request.headers.get("monnify-signature", "")
        computed_signature = hmac.new(
            settings.MONNIFY_SECRET_KEY.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        print(f"DEBUG_TRACE: Monnify Signature: {monnify_signature}")
        print(f"DEBUG_TRACE: Computed Signature: {computed_signature}")

        if computed_signature != monnify_signature:
            print("DEBUG_TRACE: SIGNATURE MISMATCH")
            if not settings.DEBUG:
                return Response({"error": "Invalid signature"}, status=400)
            print("DEBUG_TRACE: DEBUG OVERRIDE — bypassing signature check")

        # ──────────────────────────────────────────────
        # 3. JSON PARSE
        # ──────────────────────────────────────────────
        try:
            payload = json.loads(raw_body.decode("utf-8"))
            print(f"DEBUG_TRACE: Parsed Payload: {json.dumps(payload, indent=2)}")
        except Exception as e:
            print(f"DEBUG_TRACE: JSON CRASH: {str(e)}")
            return Response({"error": "JSON parse error"}, status=400)

        event_type = payload.get("eventType", "")
        event_data = payload.get("eventData", {})
        print(f"DEBUG_TRACE: Event Type: {event_type}")

        # ──────────────────────────────────────────────
        # 4. EXTRACT KEY FIELDS
        # ──────────────────────────────────────────────
        account_number = event_data.get("destinationAccountNumber")
        account_ref = event_data.get("destinationAccountReference") or event_data.get("paymentReference")
        amount_paid = Decimal(str(event_data.get("amountPaid", "0")))
        txn_ref = event_data.get("transactionReference")

        print(f"DEBUG_TRACE: account_number: {account_number}")
        print(f"DEBUG_TRACE: account_ref: {account_ref}")
        print(f"DEBUG_TRACE: amount_paid: {amount_paid}")
        print(f"DEBUG_TRACE: txn_ref: {txn_ref}")

        # ──────────────────────────────────────────────
        # 5. IDEMPOTENCY CHECK
        # ──────────────────────────────────────────────
        if txn_ref:
            from wallet.models import Transaction
            if Transaction.objects.filter(reference=txn_ref).exists():
                print(f"DEBUG_TRACE: DUPLICATE — transaction {txn_ref} already processed")
                return Response({"status": "ignored"}, status=200)

        # ──────────────────────────────────────────────
        # 6. UNIVERSAL WALLET MATCH
        #    Strategy A: account_number (most reliable)
        #    Strategy B: reference digit parsing (fallback)
        # ──────────────────────────────────────────────
        from wallet.models import Wallet

        wallet = None

        # Strategy A — search by destinationAccountNumber
        if account_number:
            print(f"DEBUG_TRACE: Attempting lookup by account_number: {account_number}")
            try:
                wallet = Wallet.objects.get(account_number=account_number)
                print(f"DEBUG_TRACE: Found wallet via account_number! User: {wallet.user_id}, Balance: {wallet.balance}")
            except Wallet.DoesNotExist:
                print(f"DEBUG_TRACE: No wallet found for account_number: {account_number}")
                wallet = None

        # Strategy B — fallback: extract user_id from reference digits
        if wallet is None and account_ref:
            ref_str = str(account_ref).strip()
            digit_match = re.findall(r"\d+", ref_str)
            if digit_match:
                user_id = digit_match[0]
                print(f"DEBUG_TRACE: Attempting lookup by user_id from reference: {user_id}")
                try:
                    wallet = Wallet.objects.get(user_id=user_id)
                    print(f"DEBUG_TRACE: Found wallet via user_id! Account: {wallet.account_number}, Balance: {wallet.balance}")
                except Wallet.DoesNotExist:
                    print(f"DEBUG_TRACE: No wallet found for user_id: {user_id}")
                    wallet = None

        if wallet is None:
            print(f"DEBUG_TRACE: CRITICAL — wallet not found via any strategy")
            return Response({"error": "Wallet not found"}, status=404)

        # ──────────────────────────────────────────────
        # 7. ATOMIC CREDIT + FEE DEDUCTION
        # ──────────────────────────────────────────────
        try:
            with transaction.atomic():
                locked_wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)

                FEE = Decimal("50.00")
                gross_amount = amount_paid
                net_amount = gross_amount - FEE
                net_credit = max(net_amount, Decimal("0.00"))

                locked_wallet.balance += net_credit
                locked_wallet.save()

                Transaction.objects.create(
                    user=locked_wallet.user,
                    trans_type="DEPOSIT",
                    amount=gross_amount,
                    fee=FEE,
                    net_amount=net_credit,
                    status="SUCCESSFUL",
                    reference=txn_ref or f"WEBHOOK-{account_number}",
                )

            print(f"DEBUG_TRACE: SUCCESS — User {locked_wallet.user_id} credited ₦{net_credit} (gross ₦{gross_amount} - fee ₦{FEE})")
            return Response({"status": "success"}, status=200)

        except Exception as e:
            print(f"DEBUG_TRACE: ATOMIC CREDIT CRASH: {str(e)}")
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
            wallet.save(update_fields=["bank_name", "account_number", "account_reference"])

            response_data = {
                "bank_name": account["bank_name"],
                "account_number": account["account_number"],
                "account_reference": account["account_reference"],
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
