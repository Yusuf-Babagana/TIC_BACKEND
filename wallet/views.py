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


@method_decorator(csrf_exempt, name="dispatch")
class MonnifyWebhookView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        print("🔔 [WEBHOOK TRACE] Endpoint hit by external server.")

        # 1. Capture the body safely before DRF alters anything further
        try:
            raw_body = request._request.body
            print("📦 [WEBHOOK TRACE] Raw body bytes captured successfully.")
        except Exception as e:
            print(f"❌ [WEBHOOK TRACE] Failed to read raw body stream: {str(e)}")
            raw_body = json.dumps(request.data).encode("utf-8")

        # 2. Extract and Log Headers
        monnify_signature = request.headers.get("monnify-signature", "")
        print(f"🔑 [WEBHOOK TRACE] Incoming Monnify Signature: {monnify_signature}")

        # 3. Calculate and Verify Signature
        computed_signature = hmac.new(
            settings.MONNIFY_SECRET_KEY.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        print(f"🔑 [WEBHOOK TRACE] Computed Signature: {computed_signature}")

        # Dev Override: If in DEBUG mode, pass even if signature fails
        if computed_signature != monnify_signature and not settings.DEBUG:
            print("❌ [WEBHOOK TRACE] Signature verification FAILED. Rejecting request.")
            return Response({"status": "error", "message": "Invalid signature"}, status=400)

        print("✅ [WEBHOOK TRACE] Signature verified or allowed by DEBUG override.")

        # 4. Parse Event Data
        payload = request.data
        event_type = payload.get("eventType")
        event_data = payload.get("eventData", {})
        print(f"📋 [WEBHOOK TRACE] Event Type: {event_type}, Status: {event_data.get('paymentStatus')}")

        if event_type == "SUCCESSFUL_TRANSACTION" and event_data.get("paymentStatus") == "PAID":
            account_ref = event_data.get("destinationAccountReference")
            amount_paid = Decimal(str(event_data.get("amountPaid", 0)))
            print(f"💰 [WEBHOOK TRACE] Processing deposit for Ref: {account_ref}, Amount: {amount_paid}")

            if account_ref:
                try:
                    user_id = account_ref.replace("TIC-", "").strip()
                    with transaction.atomic():
                        wallet = Wallet.objects.select_for_update().get(user_id=user_id)
                        wallet.balance += amount_paid
                        wallet.save()

                        Transaction.objects.create(
                            user_id=user_id,
                            trans_type="DEPOSIT",
                            amount=amount_paid,
                            status="SUCCESSFUL",
                            reference=event_data.get("transactionReference"),
                        )
                    print(f"🚀 [WEBHOOK TRACE] SUCCESS! User {user_id} wallet credited with ₦{amount_paid}")
                    return Response({"status": "success"}, status=200)
                except Exception as db_err:
                    print(f"❌ [WEBHOOK TRACE] Database/Wallet update crash: {str(db_err)}")
                    return Response({"status": "error", "message": str(db_err)}, status=500)

        print("⚠️ [WEBHOOK TRACE] Webhook event was ignored (Not a successful paid transaction).")
        return Response({"status": "ignored"}, status=200)


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
