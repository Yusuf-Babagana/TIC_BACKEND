import logging
import uuid

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from wallet.models import Transaction, Wallet

from .models import DataPlan
from .providers import TRANSACTION_TYPE_MAP
from .serializers import DataPlanSerializer, VTUPurchaseSerializer, UnifiedPurchaseSerializer
from .services import CheapDataHubService, CheapDataHubError

logger = logging.getLogger(__name__)


def _mask_key(key):
    if not key:
        return "(empty)"
    if len(key) <= 10:
        return key[:4] + "****"
    return key[:6] + "****" + key[-4:]


class DataPlanListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        network = request.query_params.get("network")
        plans = DataPlan.objects.filter(is_active=True).order_by("price")
        if network:
            plans = plans.filter(network=network.upper())
        serializer = DataPlanSerializer(plans, many=True)
        return Response(serializer.data)


class SyncDataPlansView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {"status": "false", "message": "Admin access required"},
                status=status.HTTP_403_FORBIDDEN,
            )
        ok = CheapDataHubService.sync_live_plans()
        if ok:
            return Response({"status": "true", "message": "Plans synced successfully"})
        return Response(
            {"status": "false", "message": "Plan sync failed"},
            status=status.HTTP_502_BAD_GATEWAY,
        )


class VTUPurchaseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VTUPurchaseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        service_type = data["service_type"]
        cost = data["amount"]
        user = request.user

        try:
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(user=user)

                if wallet.balance < cost:
                    return Response(
                        {
                            "status": "false",
                            "message": "Insufficient TIC Wallet balance. Please fund your account.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                result = self._call_provider(service_type, data)

                provider_status = result.get("status")
                if provider_status in ("true", True):
                    wallet.balance -= cost
                    wallet.save(update_fields=["balance"])

                    Transaction.objects.create(
                        user=user,
                        trans_type=TRANSACTION_TYPE_MAP.get(service_type, "DATA"),
                        amount=cost,
                        reference=result.get("reference") or result.get("transaction_id", "N/A"),
                        status="SUCCESSFUL",
                    )
                    return Response(result, status=status.HTTP_200_OK)

                Transaction.objects.create(
                    user=user,
                    trans_type=TRANSACTION_TYPE_MAP.get(service_type, "DATA"),
                    amount=cost,
                    reference=f"FAILED-{uuid.uuid4().hex[:12].upper()}",
                    status="FAILED",
                )
                msg = result.get("message") or result.get("error") or "Provider request failed"
                return Response(
                    {"status": "false", "message": msg},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        except CheapDataHubError as e:
            logger.error(
                "VTU provider error: service_type=%s cost=%s user=%s error=%s masked_key=%s",
                service_type, cost, user.id, str(e),
                _mask_key(settings.CHEAPDATAHUB_API_KEY),
            )
            Transaction.objects.create(
                user=user,
                trans_type=TRANSACTION_TYPE_MAP.get(service_type, "DATA"),
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
                "VTU unexpected crash: service_type=%s cost=%s user=%s error=%s masked_key=%s",
                service_type, cost, user.id, str(e),
                _mask_key(settings.CHEAPDATAHUB_API_KEY),
            )
            Transaction.objects.create(
                user=user,
                trans_type=TRANSACTION_TYPE_MAP.get(service_type, "DATA"),
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
            "AIRTIME": lambda d: CheapDataHubService.buy_airtime(
                provider_id=d.get("provider_id"),
                phone_number=d.get("phone_number"),
                amount=d.get("amount"),
            ),
            "DATA": lambda d: CheapDataHubService.buy_data(
                bundle_id=d.get("bundle_id"),
                phone_number=d.get("phone_number"),
            ),
            "ELECTRICITY": lambda d: CheapDataHubService.buy_electricity(
                disco_id=d.get("disco_id"),
                meter_number=d.get("meter_number"),
                amount=d.get("amount"),
                meter_type=d.get("meter_type"),
                phone=d.get("phone_number"),
            ),
            "CABLE": lambda d: CheapDataHubService.buy_cable(
                plan_id=d.get("plan_id"),
                card_number=d.get("card_number"),
                phone=d.get("phone_number"),
            ),
            "EXAMPIN": lambda d: CheapDataHubService.buy_exam_pin(
                product_id=d.get("product_id"),
                quantity=d.get("quantity", 1),
            ),
        }
        handler = mapping.get(service_type)
        if not handler:
            raise ValueError(f"Unsupported service_type: {service_type}")
        return handler(data)


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
        else:
            try:
                plan = DataPlan.objects.get(plan_id=plan_id)
            except DataPlan.DoesNotExist:
                return Response(
                    {"status": "false", "message": f"Unknown plan_id: {plan_id}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cost = plan.price

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
            return {"bundle_id": plan_id, "phone_number": target_id}
        if category == "AIRTIME":
            return {"provider_id": plan_id, "phone_number": target_id, "amount": str(amount)}
        if category == "CABLE":
            return {"plan_id": plan_id, "cardnumber": target_id, "phone": user.phone_number or target_id}
        if category == "ELECTRICITY":
            return {
                "disco_id": plan_id,
                "meter_number": target_id,
                "amount": str(amount),
                "meter_type": "prepaid",
                "phone": target_id,
            }
        raise CheapDataHubError(f"Unsupported category: {category}")
