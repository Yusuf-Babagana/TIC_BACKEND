import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .constants import get_data_plan, get_cable_plan
from .models import CablePlan, DataPlan
from .nellobytes import NellobytesService, NellobytesError
from .providers import disco_name_from_id, network_name_from_provider_id
from .serializers import UnifiedPurchaseSerializer

logger = logging.getLogger(__name__)



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
        from users.utils import check_transaction_pin
        from wallet.models import Wallet, Transaction

        user = request.user
        pin_ok, pin_error = check_transaction_pin(user, request.data.get("transaction_pin"))
        if not pin_ok:
            return Response({"status": "false", "message": pin_error}, status=status.HTTP_400_BAD_REQUEST)

        serializer = UnifiedPurchaseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        category = data["category"]
        target_id = data["target_id"]
        plan_id = data["plan_id"]
        amount = data.get("amount")
        provider_name = data.get("provider", "")

        if category == "DATA":
            plan = get_data_plan(plan_id, provider_name)
            if plan is None:
                return Response(
                    {"status": "false", "message": f"Unknown DATA plan_id: {plan_id} for network {provider_name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return _execute_nellobytes_data_purchase(user, provider_name, plan_id, target_id, plan["price"])

        if category == "AIRTIME":
            if amount < 100:
                return Response(
                    {"status": "false", "message": "Minimum airtime amount is ₦100"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if amount > 200000:
                return Response(
                    {"status": "false", "message": "Maximum airtime amount is ₦200,000"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return _execute_nellobytes_airtime_purchase(user, provider_name, amount, target_id)

        if category == "CABLE":
            plan = get_cable_plan(plan_id, provider_name)
            if plan is None:
                return Response(
                    {"status": "false", "message": f"Unknown CABLE plan_id: {plan_id} for provider {provider_name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            phone_no = user.phone_number or "08012345678"
            return _execute_nellobytes_cable_purchase(
                user, provider_name, plan_id, target_id, phone_no, plan["price"]
            )

        if category == "ELECTRICITY":
            if amount < 1000:
                return Response(
                    {"status": "false", "message": "Minimum electricity amount is ₦1,000"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if amount > 200000:
                return Response(
                    {"status": "false", "message": "Maximum electricity amount is ₦200,000"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            meter_type = data.get("meter_type", "PREPAID")
            phone_no = user.phone_number or "08012345678"
            return _execute_nellobytes_electricity_purchase(
                user, provider_name, meter_type, target_id, amount, phone_no
            )

        return Response(
            {"status": "false", "message": f"Unsupported category: {category}"},
            status=status.HTTP_400_BAD_REQUEST,
        )


def _execute_nellobytes_purchase(user, trans_type, cost, buy_fn):
    """
    buy_fn(request_id, callback_url) -> NellobytesService result dict,
    or raises NellobytesError. Shared by every Nellobytes-backed category:
    debit-then-reserve, PENDING transaction, resolved later by the webhook
    or the reconciliation sweep.
    """
    from wallet.models import Wallet, Transaction

    cost = Decimal(str(cost))
    request_id = f"TIC-{uuid.uuid4().hex[:16].upper()}"
    callback_url = f"{settings.PUBLIC_BASE_URL}{reverse('vtu:nellobytes-webhook')}"

    try:
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=user)

            if wallet.balance < cost:
                return Response(
                    {"status": "false", "message": "Insufficient Balance"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            result = buy_fn(request_id, callback_url)

            wallet.balance -= cost
            wallet.save(update_fields=["balance"])

            Transaction.objects.create(
                user=user,
                trans_type=trans_type,
                amount=cost,
                reference=request_id,
                order_id=result["order_id"],
                status="PENDING",
            )

            response_data = {
                "status": "pending",
                "message": f"Your {trans_type.lower()} purchase is being processed",
                "reference": request_id,
                "order_id": result["order_id"],
            }
            # Surface any extra provider fields (e.g. electricity's
            # meterno/metertoken) beyond our own normalized keys.
            reserved_keys = {"orderid", "statuscode", "status", "order_id", "status_code"}
            response_data.update({k: v for k, v in result.items() if k not in reserved_keys})

            return Response(response_data, status=status.HTTP_202_ACCEPTED)

    except NellobytesError as e:
        logger.error(
            "Nellobytes %s purchase error: cost=%s user=%s error=%s",
            trans_type, cost, user.id, str(e),
        )
        Transaction.objects.create(
            user=user,
            trans_type=trans_type,
            amount=cost,
            reference=request_id,
            status="FAILED",
        )

        # Nellobytes' own reseller balance running dry is an operational
        # problem on our side, not something the end user can act on —
        # show it as a generic outage rather than leaking "Insufficient
        # Balance" (which reads like *their* wallet is short).
        if "INSUFFICIENT_BALANCE" in str(e).upper():
            return Response(
                {
                    "status": "false",
                    "message": "This service is temporarily under maintenance. Please try again shortly.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {"status": "false", "message": str(e)},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    except Exception as e:
        logger.error(
            "Nellobytes %s purchase crash: cost=%s user=%s error=%s",
            trans_type, cost, user.id, str(e),
        )
        Transaction.objects.create(
            user=user,
            trans_type=trans_type,
            amount=cost,
            reference=request_id,
            status="FAILED",
        )
        return Response(
            {
                "status": "false",
                "message": "Service temporarily unavailable. Please try again.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def _execute_nellobytes_data_purchase(user, network, plan_id, mobile_number, cost):
    return _execute_nellobytes_purchase(
        user, "DATA", cost,
        lambda request_id, callback_url: NellobytesService.buy_data(
            network=network, plan_id=plan_id, mobile_number=mobile_number,
            request_id=request_id, callback_url=callback_url,
        ),
    )


def _execute_nellobytes_airtime_purchase(user, network, amount, mobile_number):
    return _execute_nellobytes_purchase(
        user, "AIRTIME", amount,
        lambda request_id, callback_url: NellobytesService.buy_airtime(
            network=network, amount=int(amount), mobile_number=mobile_number,
            request_id=request_id, callback_url=callback_url,
        ),
    )


def _execute_nellobytes_cable_purchase(user, cable_tv, package, smartcard_no, phone_no, cost):
    return _execute_nellobytes_purchase(
        user, "UTILITY", cost,
        lambda request_id, callback_url: NellobytesService.buy_cable(
            cable_tv=cable_tv, package=package, smartcard_no=smartcard_no, phone_no=phone_no,
            request_id=request_id, callback_url=callback_url,
        ),
    )


def _execute_nellobytes_electricity_purchase(user, company, meter_type, meter_no, amount, phone_no):
    return _execute_nellobytes_purchase(
        user, "UTILITY", amount,
        lambda request_id, callback_url: NellobytesService.buy_electricity(
            company=company, meter_type=meter_type, meter_no=meter_no, amount=int(amount),
            phone_no=phone_no, request_id=request_id, callback_url=callback_url,
        ),
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
        if cost > 200000:
            return Response(
                {"status": "false", "message": "Maximum airtime amount is ₦200,000"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        network = network_name_from_provider_id(provider_id)
        if not network:
            return Response(
                {"status": "false", "message": f"Unknown provider_id: {provider_id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return _execute_nellobytes_airtime_purchase(request.user, network, cost, phone_number)


class DataPurchaseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        bundle_id = request.data.get("bundle_id")
        phone_number = request.data.get("phone_number")
        network = request.data.get("network") or request.data.get("provider")

        if not all([bundle_id, phone_number, network]):
            return Response(
                {"status": "false", "message": "bundle_id, phone_number, and network are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan = DataPlan.objects.filter(
            network=network.upper(), plan_id=str(bundle_id), is_active=True
        ).first()
        if plan is None:
            return Response(
                {"status": "false", "message": f"Unknown plan_id: {bundle_id} for network {network}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return _execute_nellobytes_data_purchase(
            request.user, network, plan.plan_id, phone_number, plan.selling_price
        )


class ElectricityPurchaseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        disco_id = request.data.get("disco_id")
        meter_number = request.data.get("meter_number")
        amount = request.data.get("amount")
        meter_type = request.data.get("meter_type", "PREPAID")
        phone = request.data.get("phone")

        if not all([disco_id, meter_number, amount, phone]):
            return Response(
                {"status": "false", "message": "disco_id, meter_number, amount, and phone are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cost = Decimal(str(amount))
        if cost < 1000:
            return Response(
                {"status": "false", "message": "Minimum electricity amount is ₦1,000"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if cost > 200000:
            return Response(
                {"status": "false", "message": "Maximum electricity amount is ₦200,000"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company = disco_name_from_id(disco_id)
        if not company:
            return Response(
                {"status": "false", "message": f"Unknown disco_id: {disco_id}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return _execute_nellobytes_electricity_purchase(
            request.user, company, meter_type, meter_number, cost, phone
        )


class CablePurchaseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get("plan_id")
        card_number = request.data.get("cardnumber") or request.data.get("card_number")
        phone = request.data.get("phone")
        provider_name = request.data.get("provider") or request.data.get("cable_tv")

        if not all([plan_id, card_number, phone, provider_name]):
            return Response(
                {"status": "false", "message": "plan_id, cardnumber, phone, and provider are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan = CablePlan.objects.filter(
            provider_name=provider_name.upper(), plan_id=str(plan_id), is_active=True
        ).first()
        if plan is None:
            return Response(
                {"status": "false", "message": f"Unknown plan_id: {plan_id} for provider {provider_name}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return _execute_nellobytes_cable_purchase(
            request.user, provider_name, plan.plan_id, card_number, phone, plan.selling_price
        )


class CableVerifyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cable_tv = request.query_params.get("cable_tv") or request.query_params.get("provider")
        smartcard_no = request.query_params.get("smartcard_no")

        if not cable_tv or not smartcard_no:
            return Response(
                {"status": "false", "message": "cable_tv and smartcard_no are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            customer_name = NellobytesService.verify_smartcard(cable_tv, smartcard_no)
        except NellobytesError as e:
            return Response({"status": "false", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"status": "true", "customer_name": customer_name}, status=status.HTTP_200_OK)


class MeterVerifyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = request.query_params.get("company") or request.query_params.get("provider")
        meter_no = request.query_params.get("meter_no")
        meter_type = request.query_params.get("meter_type", "PREPAID")

        if not company or not meter_no:
            return Response(
                {"status": "false", "message": "company and meter_no are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            customer_name = NellobytesService.verify_meter(company, meter_no, meter_type)
        except NellobytesError as e:
            return Response({"status": "false", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"status": "true", "customer_name": customer_name}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class NellobytesCallbackView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        return self._handle(request.query_params)

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else request.query_params
        return self._handle(data)

    def _handle(self, data):
        from wallet.models import Transaction

        order_id = data.get("orderid")
        request_id = data.get("requestid")

        logger.info(
            "Nellobytes callback received: order_id=%s request_id=%s (fields beyond these are untrusted)",
            order_id, request_id,
        )

        txn = None
        if order_id:
            txn = Transaction.objects.filter(order_id=order_id).first()
        if txn is None and request_id:
            txn = Transaction.objects.filter(reference=request_id).first()

        if txn is None:
            logger.error(
                "Nellobytes callback: no matching Transaction for order_id=%s request_id=%s",
                order_id, request_id,
            )
            return Response({"status": "not_found"}, status=404)

        if txn.status != "PENDING":
            # Already resolved — nothing to do. Also means we never re-derive an
            # outcome from a stale/replayed callback.
            return Response({"status": "already_resolved"}, status=200)

        # Nellobytes doesn't sign this callback, so its orderstatus/statuscode
        # fields are untrusted — anyone who knows their own order_id/reference
        # (both are handed back in the purchase response) could otherwise POST
        # a forged "FAILED" here to get refunded for an order that actually
        # succeeded. Instead, use the callback purely as a "check now" trigger
        # and resolve the real outcome via our own server-to-server query —
        # the same call the reconciliation sweep uses.
        try:
            body = NellobytesService.query_order(order_id=txn.order_id)
        except NellobytesError as e:
            logger.error(
                "Nellobytes callback: query_order failed for order_id=%s: %s",
                txn.order_id, e,
            )
            return Response({"status": "query_failed"}, status=502)

        outcome = NellobytesService.resolve_order_outcome(
            body.get("orderstatus") or body.get("status"), body.get("statuscode")
        )
        NellobytesService.apply_order_outcome(txn.pk, outcome)

        return Response({"status": "acknowledged"}, status=200)
