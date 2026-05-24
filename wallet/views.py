import hashlib
import hmac
import logging
import re
import traceback

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
        expected = hmac.new(
            settings.MONNIFY_SECRET_KEY.encode("utf-8"),
            request.body,
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    @staticmethod
    def _extract_account_reference(data):
        return (
            data.get("metaData", {}).get("accountReference")
            or data.get("eventData", {}).get("metaData", {}).get("accountReference")
            or data.get("eventData", {}).get("product", {}).get("reference")
        )

    def post(self, request):
        if not self._verify_signature(request):
            return Response({"status": "invalid signature"}, status=403)

        data = request.data
        event_data = data.get("eventData", data)

        if event_data.get("paymentStatus") == "PAID":
            ref = event_data.get("paymentReference")
            amount = float(event_data.get("amountPaid", 0))

            account_ref = self._extract_account_reference(data)
            customer_email = event_data.get("customer", {}).get("email")

            try:
                with transaction.atomic():
                    if account_ref:
                        wallet = Wallet.objects.select_for_update().get(
                            account_reference=account_ref
                        )
                    elif customer_email:
                        wallet = Wallet.objects.select_for_update().get(
                            user__email=customer_email
                        )
                    else:
                        return Response(
                            {"status": "error", "message": "No wallet identifier found"},
                            status=400,
                        )

                    wallet.balance += amount
                    wallet.save(update_fields=["balance"])

                    Transaction.objects.create(
                        user=wallet.user,
                        trans_type="DEPOSIT",
                        amount=amount,
                        reference=ref,
                        status="SUCCESSFUL",
                    )

                return Response({"status": "success"}, status=200)

            except Wallet.DoesNotExist:
                return Response({"status": "error", "message": "Wallet not found"}, status=404)

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
