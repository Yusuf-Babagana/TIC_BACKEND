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

        # 1. TRACE INPUT
        print(f"DEBUG_TRACE: Received Request Length: {len(raw_body)} bytes")

        # 2. SIGNATURE TRACE
        monnify_signature = request.headers.get("monnify-signature", "MISSING")
        print(f"DEBUG_TRACE: Monnify Signature: {monnify_signature}")

        # 3. JSON PARSE TRACE
        try:
            payload = json.loads(raw_body.decode("utf-8"))
            print(f"DEBUG_TRACE: Parsed Payload: {json.dumps(payload, indent=2)}")
        except Exception as e:
            print(f"DEBUG_TRACE: JSON CRASH: {str(e)}")
            return Response({"error": "JSON parse error"}, status=400)

        # 4. REFERENCE EXTRACTION TRACE
        event_data = payload.get("eventData", {})
        ref = event_data.get("destinationAccountReference") or event_data.get("paymentReference")
        print(f"DEBUG_TRACE: Extracted Reference: {ref}")

        # 5. USER LOOKUP TRACE
        try:
            import re

            digit_match = re.findall(r"\d+", str(ref))
            user_id = digit_match[0] if digit_match else None
            print(f"DEBUG_TRACE: Resolved User ID: {user_id}")

            from wallet.models import Wallet

            wallet = Wallet.objects.get(user_id=user_id)
            print(f"DEBUG_TRACE: Wallet found! Current Balance: {wallet.balance}")

            # 6. CALCULATION TRACE
            amount = Decimal(str(event_data.get("amountPaid", "0")))
            print(f"DEBUG_TRACE: Amount to credit: {amount}")

        except Exception as e:
            print(f"DEBUG_TRACE: DATABASE/LOOKUP CRASH: {str(e)}")
            return Response({"error": "Lookup failed"}, status=500)

        return Response({"status": "debug_complete"}, status=200)


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
