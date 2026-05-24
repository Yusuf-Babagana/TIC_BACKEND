import hashlib
import hmac
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

    def _verify_signature(self, request):
        signature = request.headers.get("monnify-signature")
        if not signature:
            return False
        raw_body = request.body
        expected = hmac.new(
            settings.MONNIFY_SECRET_KEY.encode("utf-8"),
            raw_body,
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    def post(self, request, *args, **kwargs):
        if not self._verify_signature(request):
            print("❌ Webhook signature verification failed")
            return Response({"status": "invalid signature"}, status=403)

        print("📨 INCOMING MONNIFY WEBHOOK BODY:", request.data)

        payload = request.data
        event_type = payload.get("eventType")
        event_data = payload.get("eventData", {})

        if event_type == "SUCCESSFUL_TRANSACTION" or event_data.get("paymentStatus") == "PAID":
            account_ref = (
                event_data.get("destinationAccountReference")
                or event_data.get("paymentReference")
            )
            amount_paid = Decimal(str(event_data.get("amountPaid", 0)))

            if account_ref:
                try:
                    user_id = account_ref.replace("TIC-", "").strip()

                    with transaction.atomic():
                        wallet = Wallet.objects.select_for_update().get(
                            user_id=user_id
                        )
                        wallet.balance += amount_paid
                        wallet.save(update_fields=["balance"])

                        Transaction.objects.create(
                            user_id=user_id,
                            trans_type="DEPOSIT",
                            amount=amount_paid,
                            status="SUCCESSFUL",
                            reference=event_data.get("transactionReference"),
                        )

                    print(f"✅ Successfully credited User ID {user_id} with ₦{amount_paid}")
                    return Response({"status": "success"}, status=200)

                except Wallet.DoesNotExist:
                    print(f"❌ No wallet found for account_ref: {account_ref}")
                    return Response(
                        {"status": "error", "message": "Wallet not found"},
                        status=404,
                    )
                except Exception as e:
                    print(f"❌ Webhook database processing error: {str(e)}")
                    return Response(
                        {"status": "error", "message": str(e)},
                        status=500,
                    )

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
