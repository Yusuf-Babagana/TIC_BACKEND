import logging
import uuid

from django.conf import settings
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from wallet.models import Transaction, Wallet

from .constants import DATA_PLANS, CABLE_PLANS, get_data_plan, get_cable_plan
from .providers import TRANSACTION_TYPE_MAP
from .serializers import UnifiedPurchaseSerializer
from .services import CheapDataHubService, CheapDataHubError

logger = logging.getLogger(__name__)


def _mask_key(key):
    if not key:
        return "(empty)"
    if len(key) <= 10:
        return key[:4] + "****"
    return key[:6] + "****" + key[-4:]


@method_decorator(csrf_exempt, name="dispatch")
class DataPlanListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        category = request.query_params.get("category", "").upper()
        provider = request.query_params.get("provider", "").lower()

        if category == "DATA":
            filtered = [p for p in DATA_PLANS if p["provider"] == provider]
            return Response(filtered, status=200)

        if category == "CABLE":
            filtered = [c for c in CABLE_PLANS if c["provider"] == provider.upper()]
            return Response(filtered, status=200)

        return Response([], status=400)


class UnifiedPurchaseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UnifiedPurchaseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        category = data["category"]
        target_id = data["target_id"]
        plan_id = data["plan_id"]
        amount = data.get("amount")
        user = request.user

        if category in ("AIRTIME", "ELECTRICITY"):
            cost = amount
        elif category == "DATA":
            plan = get_data_plan(plan_id)
            if plan is None:
                return Response(
                    {"status": "false", "message": f"Unknown DATA plan_id: {plan_id}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cost = plan["price"]
        elif category == "CABLE":
            plan = get_cable_plan(plan_id)
            if plan is None:
                return Response(
                    {"status": "false", "message": f"Unknown CABLE plan_id: {plan_id}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cost = plan["price"]
        else:
            return Response(
                {"status": "false", "message": f"Unsupported category: {category}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(user=user)

                if wallet.balance < cost:
                    return Response(
                        {"status": "false", "message": "Insufficient Balance"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                payload = self._build_payload(category, plan_id, target_id, amount, user)
                result = CheapDataHubService.purchase(category, payload)

                provider_status = result.get("status")
                if provider_status in ("true", True):
                    wallet.balance -= cost
                    wallet.save(update_fields=["balance"])

                    Transaction.objects.create(
                        user=user,
                        trans_type=TRANSACTION_TYPE_MAP[category],
                        amount=cost,
                        reference=result.get("reference") or result.get("transaction_id", "N/A"),
                        status="SUCCESSFUL",
                    )
                    return Response(result, status=status.HTTP_200_OK)

                msg = result.get("message") or result.get("error") or "Provider request failed"
                raise CheapDataHubError(msg)

        except CheapDataHubError as e:
            logger.error(
                "VTU unified purchase error: category=%s cost=%s user=%s error=%s masked_key=%s",
                category, cost, user.id, str(e),
                _mask_key(settings.CHEAPDATAHUB_API_KEY),
            )
            Transaction.objects.create(
                user=user,
                trans_type=TRANSACTION_TYPE_MAP[category],
                amount=cost,
                reference=f"FAILED-{uuid.uuid4().hex[:12].upper()}",
                status="FAILED",
            )
            return Response(
                {"status": "false", "message": str(e)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except Exception as e:
            logger.error(
                "VTU unified purchase crash: category=%s cost=%s user=%s error=%s masked_key=%s",
                category, cost, user.id, str(e),
                _mask_key(settings.CHEAPDATAHUB_API_KEY),
            )
            Transaction.objects.create(
                user=user,
                trans_type=TRANSACTION_TYPE_MAP[category],
                amount=cost,
                reference=f"FAILED-{uuid.uuid4().hex[:12].upper()}",
                status="FAILED",
            )
            return Response(
                {
                    "status": "false",
                    "message": "Service temporarily unavailable. Please try again.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @staticmethod
    def _build_payload(category, plan_id, target_id, amount, user):
        if category == "DATA":
            return {"bundle_id": int(plan_id), "phone_number": target_id}
        if category == "AIRTIME":
            return {"provider_id": int(plan_id), "phone_number": target_id, "amount": str(amount)}
        if category == "CABLE":
            return {"plan_id": int(plan_id), "cardnumber": target_id, "phone": user.phone_number or "08012345678"}
        if category == "ELECTRICITY":
            return {
                "disco_id": int(plan_id),
                "meter_number": target_id,
                "amount": str(amount),
                "meter_type": "prepaid",
                "phone": target_id,
            }
        raise CheapDataHubError(f"Unsupported category: {category}")
