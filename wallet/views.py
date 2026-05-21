import hashlib
import hmac
import logging
import re
import traceback

from django.conf import settings
from rest_framework import generics, status

logger = logging.getLogger(__name__)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Wallet, Transaction
from .monnify import MonnifyService, MonnifyError
from .serializers import TransactionSerializer


class WalletBalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = request.user.wallet
        return Response({
            "balance": str(wallet.balance),
            "bank_name": wallet.bank_name,
            "account_number": wallet.account_number,
        }, status=200)


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

    def post(self, request):
        if not self._verify_signature(request):
            return Response({"status": "invalid signature"}, status=403)

        data = request.data

        if data.get("paymentStatus") == "PAID":
            ref = data.get("paymentReference")
            amount = float(data.get("amountPaid"))
            customer_email = data["customer"]["email"]

            try:
                wallet = Wallet.objects.get(user__email=customer_email)
                wallet.balance += amount
                wallet.save()

                Transaction.objects.create(
                    user=wallet.user,
                    trans_type="DEPOSIT",
                    amount=amount,
                    reference=ref,
                    status="SUCCESSFUL",
                )
                return Response({"status": "success"}, status=200)
            except Wallet.DoesNotExist:
                return Response({"status": "error"}, status=404)

        return Response({"status": "ignored"}, status=200)


class TransactionHistoryView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user).order_by(
            "-created_at"
        )


class GenerateAccountView(APIView):
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
    permission_classes = [IsAuthenticated]

    def post(self, request):
        bvn = request.data.get("bvn", "").strip()
        nin = request.data.get("nin", "").strip()

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
