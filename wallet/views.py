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
        account_number = event_data.get("destinationAccountNumber")
        txn_ref = str(event_data.get("transactionReference", ""))
        account_ref = str(event_data.get("destinationAccountReference") or event_data.get("paymentReference") or "")

        print(f"DEBUG: amount={amount_paid} account={account_number} txn_ref={txn_ref} account_ref={account_ref}")

        from wallet.models import Wallet, Transaction

        # 3. Resolve user_id from transactionReference (format: MNFY|16|...)
        user_id = None
        parts = txn_ref.split("|")
        if len(parts) >= 2 and parts[1].isdigit():
            user_id = int(parts[1])
            print(f"DEBUG: Extracted user_id={user_id} from txn_ref")

        # 4. Find the correct wallet — NO .first() fallback
        wallet = None

        # Strategy A: user_id from txn_ref (most reliable)
        if user_id is not None:
            try:
                wallet = Wallet.objects.get(user_id=user_id)
                print(f"DEBUG: Found wallet by user_id={user_id}: account={wallet.account_number}")
            except Wallet.DoesNotExist:
                print(f"DEBUG: No wallet for user_id={user_id}")

        # Strategy B: account_number from payload
        if wallet is None and account_number:
            try:
                wallet = Wallet.objects.get(account_number=account_number)
                print(f"DEBUG: Found wallet by account_number={account_number}: user={wallet.user_id}")
            except Wallet.DoesNotExist:
                print(f"DEBUG: No wallet for account_number={account_number}")

        # Strategy C: digits from account_ref (legacy format like ABDTIC-16)
        if wallet is None and account_ref and account_ref != "None":
            digit_match = re.findall(r"\d+", account_ref)
            if digit_match:
                try:
                    wallet = Wallet.objects.get(user_id=int(digit_match[0]))
                    print(f"DEBUG: Found wallet by ref digits={digit_match[0]}: account={wallet.account_number}")
                except Wallet.DoesNotExist:
                    print(f"DEBUG: No wallet for ref user_id={digit_match[0]}")

        if wallet is None:
            print(f"DEBUG: CRITICAL — wallet not found for any strategy")
            return Response({"error": "Wallet not found"}, status=404)

        # 5. Idempotency check
        if txn_ref and txn_ref != "None":
            if Transaction.objects.filter(reference=txn_ref).exists():
                print(f"DEBUG: Duplicate — {txn_ref} already processed")
                return Response({"status": "ignored"}, status=200)

        # 6. Atomic credit + fee deduction
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
