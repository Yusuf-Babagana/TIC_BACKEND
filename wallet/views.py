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
    media_type = "application/json"

    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read()


@method_decorator(csrf_exempt, name="dispatch")
class MonnifyWebhookView(APIView):
    permission_classes = []
    authentication_classes = []
    parser_classes = [RawJsonPassthroughParser]

    def post(self, request, *args, **kwargs):
        print("🔔 [WEBHOOK TRACE] Endpoint hit successfully.")
        raw_body = request.data

        # 1. Signature validation tracking
        monnify_signature = request.headers.get("monnify-signature", "")
        computed_signature = hmac.new(
            settings.MONNIFY_SECRET_KEY.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if computed_signature != monnify_signature:
            print(f"⚠️ [WEBHOOK TRACE] Signature mismatch! Monnify sent: {monnify_signature}, Computed: {computed_signature}")
            if not settings.DEBUG:
                print("❌ [WEBHOOK TRACE] Rejecting request due to production safety rules.")
                return Response({"status": "error", "message": "Invalid signature"}, status=400)
            print("🔧 [DEBUG OVERRIDE] Proceeding anyway because DEBUG is enabled.")

        # 2. Parse JSON safely
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            print(f"❌ [WEBHOOK TRACE] JSON Decoding Crash: {str(e)}")
            return Response({"status": "error", "message": "Invalid JSON encoding"}, status=400)

        event_type = payload.get("eventType", "")
        event_data = payload.get("eventData", {})
        print(f"📋 [WEBHOOK TRACE] Event: {event_type} | Payment Status: {event_data.get('paymentStatus')}")

        # 3. Flexible Reference and Amount Extraction
        account_ref = (
            event_data.get("destinationAccountReference")
            or event_data.get("paymentReference")
            or (event_data.get("product") or {}).get("reference")
        )
        account_number = event_data.get("destinationAccountNumber") or event_data.get("accountNumber")
        amount_paid = Decimal(str(event_data.get("amountPaid", event_data.get("amount", "0.00"))))

        if account_ref:
            ref_str = str(account_ref).strip()
            print(f"📋 [WEBHOOK TRACE] Raw Reference caught: {ref_str}")
            digit_match = re.findall(r"\d+", ref_str)
            if digit_match:
                user_id = digit_match[0]
                print(f"🎯 [WEBHOOK TRACE] Extracted clean Integer User ID: {user_id}")
            else:
                print(f"❌ [WEBHOOK TRACE] No digits found in reference: {ref_str}")
                return Response({"status": "error", "message": "No numeric user ID in reference"}, status=400)
        elif account_number:
            print(f"📋 [WEBHOOK TRACE] No reference, falling back to account_number: {account_number}")
            user_id = None
        else:
            print("❌ [WEBHOOK TRACE] Failure: No reference, no account number in payload.")
            return Response({"status": "error", "message": "Missing reference"}, status=400)

        from wallet.models import Wallet, Transaction

        try:
            with transaction.atomic():
                if user_id is not None:
                    wallet = Wallet.objects.select_for_update().get(user_id=user_id)
                elif account_number:
                    print(f"💰 [WEBHOOK TRACE] Looking up by account_number: {account_number}")
                    wallet = Wallet.objects.select_for_update().get(account_number=account_number)
                else:
                    return Response({"status": "error", "message": "No matching wallet strategy"}, status=404)

                wallet.balance += amount_paid
                wallet.save()

                Transaction.objects.create(
                    user_id=wallet.user_id,
                    trans_type="DEPOSIT",
                    amount=amount_paid,
                    status="SUCCESSFUL",
                    reference=event_data.get("transactionReference", "WEBHOOK-DEP"),
                )
            print(f"🚀 [WEBHOOK TRACE] SUCCESS! User ID {wallet.user_id} wallet credited with ₦{amount_paid}")
            return Response({"status": "success"}, status=200)

        except Wallet.DoesNotExist:
            ref_display = account_ref or account_number
            print(f"❌ [WEBHOOK TRACE] Wallet mapping failed for Ref: {ref_display}")
            return Response({"status": "error", "message": "Wallet not found"}, status=404)
        except Exception as db_err:
            print(f"❌ [WEBHOOK TRACE] Final processing crash error: {str(db_err)}")
            return Response({"status": "error", "message": str(db_err)}, status=500)


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
