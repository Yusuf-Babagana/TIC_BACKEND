import logging
import uuid

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def _mask_key(key):
    if not key:
        return "(empty)"
    if len(key) <= 10:
        return key[:4] + "****"
    return key[:6] + "****" + key[-4:]
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from wallet.models import Transaction

from .models import DataPlan
from .serializers import DataPlanSerializer, VTUPurchaseSerializer
from .services import CheapDataHubService


class DataPlanListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        network = request.query_params.get("network")
        plans = DataPlan.objects.filter(is_active=True)
        if network:
            plans = plans.filter(network=network.upper())
        serializer = DataPlanSerializer(plans, many=True)
        return Response(serializer.data)


class VTUPurchaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VTUPurchaseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        service_type = data["service_type"]
        cost = data["amount"]
        user = request.user

        if user.wallet.balance < cost:
            return Response(
                {"status": "false", "message": "Insufficient TIC Wallet balance"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                result = self._call_provider(service_type, data)
                raw = result.get("status") == "true"

                if raw:
                    user.wallet.balance -= cost
                    user.wallet.save(update_fields=["balance"])

                    Transaction.objects.create(
                        user=user,
                        trans_type=self._map_transaction_type(service_type),
                        amount=cost,
                        reference=result.get("reference", "N/A"),
                        status="SUCCESSFUL",
                    )
                    return Response(result, status=status.HTTP_200_OK)
                else:
                    Transaction.objects.create(
                        user=user,
                        trans_type=self._map_transaction_type(service_type),
                        amount=cost,
                        reference=f"FAILED-{uuid.uuid4().hex[:12].upper()}",
                        status="FAILED",
                    )
                    return Response(
                        {
                            "status": "false",
                            "message": result.get(
                                "message", "Provider request failed"
                            ),
                        },
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

        except Exception:
            logger.error(
                "VTU purchase failed. service_type=%s cost=%s user=%s masked_key=%s",
                service_type,
                cost,
                user.id,
                _mask_key(settings.CHEAPDATAHUB_API_KEY),
            )
            Transaction.objects.create(
                user=user,
                trans_type=self._map_transaction_type(service_type),
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

    def _call_provider(self, service_type, data):
        mapping = {
            "AIRTIME": lambda d: CheapDataHubService.purchase_airtime(
                provider_id=d.get("provider_id"),
                phone_number=d.get("phone_number"),
                amount=d.get("amount"),
            ),
            "DATA": lambda d: CheapDataHubService.purchase_data(
                bundle_id=d.get("bundle_id"),
                phone_number=d.get("phone_number"),
            ),
            "ELECTRICITY": lambda d: CheapDataHubService.purchase_electricity(
                disco_id=d.get("disco_id"),
                meter_number=d.get("meter_number"),
                amount=d.get("amount"),
                meter_type=d.get("meter_type"),
                phone=d.get("phone_number"),
            ),
            "CABLE": lambda d: CheapDataHubService.purchase_cable(
                plan_id=d.get("plan_id"),
                card_number=d.get("card_number"),
                phone=d.get("phone_number"),
            ),
            "EXAMPIN": lambda d: CheapDataHubService.purchase_exam_pin(
                product_id=d.get("product_id"),
                quantity=d.get("quantity", 1),
            ),
        }
        handler = mapping.get(service_type)
        if not handler:
            raise ValueError(f"Unsupported service_type: {service_type}")
        return handler(data)

    @staticmethod
    def _map_transaction_type(service_type):
        mapping = {
            "AIRTIME": "AIRTIME",
            "DATA": "DATA",
            "ELECTRICITY": "UTILITY",
            "CABLE": "UTILITY",
            "EXAMPIN": "EXAMPIN",
        }
        return mapping.get(service_type, "DATA")
