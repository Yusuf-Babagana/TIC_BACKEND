import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .constants import get_data_plan, get_cable_plan, DATA_PLANS
from .models import CablePlan, DataPlan
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
            qs = DataPlan.objects.filter(is_active=True)
            if provider:
                qs = qs.filter(network=provider.upper())
            plans = [
                {
                    "id": p.plan_id,
                    "provider": p.network.lower(),
                    "name": p.plan_name,
                    "price": float(p.selling_price),
                }
                for p in qs
            ]
            return Response(plans, status=200)

        if category == "CABLE":
            qs = CablePlan.objects.filter(is_active=True)
            if provider:
                qs = qs.filter(provider_name=provider.upper())
            plans = [
                {
                    "id": p.plan_id,
                    "provider": p.provider_name,
                    "name": p.plan_name,
                    "price": float(p.selling_price),
                }
                for p in qs
            ]
            return Response(plans, status=200)

        return Response([], status=400)


class UnifiedPurchaseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from wallet.models import Wallet, Transaction

        serializer = UnifiedPurchaseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        category = data["category"]
        target_id = data["target_id"]
        plan_id = data["plan_id"]
        amount = data.get("amount")
        provider_name = data.get("provider", "")
        user = request.user

        if category in ("AIRTIME", "ELECTRICITY"):
            cost = amount
            if category == "AIRTIME" and cost < 100:
                return Response(
                    {"status": "false", "message": "Minimum airtime amount is ₦100"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
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

                payload = self._build_payload(category, plan_id, target_id, amount, provider_name, user)
                result = CheapDataHubService.purchase(category, payload)

                provider_status = result.get("status")
                if provider_status in ("true", True):
                    wallet.balance -= cost
                    wallet.save(update_fields=["balance"])

                    Transaction.objects.create(
                        user=user,
                        trans_type=TRANSACTION_TYPE_MAP[category],
                        amount=cost,
                        reference=result.get("reference")
                                  or result.get("transaction_id")
                                  or f"SUCCESS-{uuid.uuid4().hex[:12].upper()}",
                        status="SUCCESSFUL",
                    )

                    from users.utils import reward_referrer_on_first_purchase
                    reward_referrer_on_first_purchase(user)

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
    def _build_payload(category, plan_id, target_id, amount, provider_name, user):
        if category == "DATA":
            return {"bundle_id": int(plan_id), "phone_number": target_id}
        if category == "AIRTIME":
            from vtu.providers import resolve_network_id
            provider_id = resolve_network_id(provider_name) or int(plan_id)
            return {"provider_id": provider_id, "phone_number": target_id, "amount": int(amount)}
        if category == "CABLE":
            return {"plan_id": int(plan_id), "cardnumber": target_id, "phone": user.phone_number or "08012345678"}
        if category == "ELECTRICITY":
            return {
                "disco_id": int(plan_id),
                "meter_number": target_id,
                "amount": int(amount),
                "meter_type": "prepaid",
                "phone": target_id,
            }
        raise CheapDataHubError(f"Unsupported category: {category}")


def _execute_purchase(user, category, cost, provider_payload):
    from wallet.models import Wallet, Transaction

    try:
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=user)

            if wallet.balance < cost:
                return Response(
                    {"status": "false", "message": "Insufficient Balance"},
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )

            result = CheapDataHubService.purchase(category, provider_payload)
            logger.info(
                "VTU response: category=%s payload=%s result=%s",
                category, provider_payload, result,
            )

            provider_status = result.get("status")
            if provider_status in ("true", True):
                wallet.balance -= cost
                wallet.save(update_fields=["balance"])

                Transaction.objects.create(
                    user=user,
                    trans_type=TRANSACTION_TYPE_MAP[category],
                    amount=cost,
                    reference=result.get("reference")
                              or result.get("transaction_id")
                              or f"SUCCESS-{uuid.uuid4().hex[:12].upper()}",
                    status="SUCCESSFUL",
                )

                from users.utils import reward_referrer_on_first_purchase
                reward_referrer_on_first_purchase(user)

                return Response(result, status=status.HTTP_200_OK)

            msg = result.get("message") or result.get("error") or "Provider request failed"
            raise CheapDataHubError(msg)

    except CheapDataHubError as e:
        logger.error(
            "VTU purchase error: category=%s cost=%s user=%s error=%s masked_key=%s",
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
            "VTU purchase crash: category=%s cost=%s user=%s error=%s masked_key=%s",
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


class AirtimePurchaseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        provider_id = request.data.get("provider_id")
        phone_number = request.data.get("phone_number")
        amount = request.data.get("amount")

        if not all([provider_id, phone_number, amount]):
            return Response(
                {"status": "false", "message": "provider_id, phone_number, and amount are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cost = Decimal(str(amount))
        if cost < 100:
            return Response(
                {"status": "false", "message": "Minimum airtime amount is ₦100"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = {
            "provider_id": int(provider_id),
            "phone_number": phone_number,
            "amount": int(cost),
        }
        return _execute_purchase(request.user, "AIRTIME", cost, payload)


class DataPurchaseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        bundle_id = request.data.get("bundle_id")
        phone_number = request.data.get("phone_number")

        if not all([bundle_id, phone_number]):
            return Response(
                {"status": "false", "message": "bundle_id and phone_number are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan = DataPlan.objects.filter(plan_id=bundle_id, is_active=True).first()
        if plan is None:
            return Response(
                {"status": "false", "message": f"Unknown bundle_id: {bundle_id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cost = plan.selling_price
        payload = {"bundle_id": plan.bundle_id, "phone_number": phone_number}
        return _execute_purchase(request.user, "DATA", cost, payload)


class ElectricityPurchaseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        disco_id = request.data.get("disco_id")
        meter_number = request.data.get("meter_number")
        amount = request.data.get("amount")
        meter_type = request.data.get("meter_type", "prepaid")
        phone = request.data.get("phone")

        if not all([disco_id, meter_number, amount, phone]):
            return Response(
                {"status": "false", "message": "disco_id, meter_number, amount, and phone are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cost = Decimal(str(amount))
        payload = {
            "disco_id": int(disco_id),
            "meter_number": meter_number,
            "amount": int(cost),
            "meter_type": meter_type,
            "phone": phone,
        }
        return _execute_purchase(request.user, "ELECTRICITY", cost, payload)


class CablePurchaseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get("plan_id")
        card_number = request.data.get("cardnumber") or request.data.get("card_number")
        phone = request.data.get("phone")

        if not all([plan_id, card_number, phone]):
            return Response(
                {"status": "false", "message": "plan_id, cardnumber, and phone are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan = CablePlan.objects.filter(plan_id=plan_id, is_active=True).first()
        if plan is None:
            return Response(
                {"status": "false", "message": f"Unknown plan_id: {plan_id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cost = plan.selling_price
        payload = {"plan_id": plan.plan_id, "card_number": card_number, "phone": phone}
        return _execute_purchase(request.user, "CABLE", cost, payload)
