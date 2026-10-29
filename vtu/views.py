import logging
import re
from decimal import Decimal

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .constants import get_data_plan, get_cable_plan
from .models import CablePlan, DataPlan, ServicePricing
from .pricing import customer_price
from .gateway import registry, router
from .gateway.base import CustomerVerificationError
from .gateway.types import PurchaseRequest, Service
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

        if category in ("AIRTIME", "ELECTRICITY"):
            # No fixed plans — expose the admin's pricing rules so the app can
            # show "you pay X" before purchase.
            qs = ServicePricing.objects.filter(category=category, is_active=True)
            if provider:
                qs = qs.filter(provider__in=[provider.upper(), "*"])
            return Response(
                [
                    {
                        "provider": r.provider,
                        "percent_adjust": float(r.percent_adjust),
                        "flat_fee": float(r.flat_fee),
                    }
                    for r in qs
                ],
                status=200,
            )

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
            return _execute_nellobytes_data_purchase(
                user, provider_name, plan_id, target_id, plan["price"],
                idempotency_key=_idempotency_key(request),
            )

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
            return _execute_nellobytes_airtime_purchase(
                user, provider_name, amount, target_id, idempotency_key=_idempotency_key(request)
            )

        if category == "CABLE":
            plan = get_cable_plan(plan_id, provider_name)
            if plan is None:
                return Response(
                    {"status": "false", "message": f"Unknown CABLE plan_id: {plan_id} for provider {provider_name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            phone_no = user.phone_number or "08012345678"
            return _execute_nellobytes_cable_purchase(
                user, provider_name, plan_id, target_id, phone_no, plan["price"],
                idempotency_key=_idempotency_key(request),
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
                user, provider_name, meter_type, target_id, amount, phone_no,
                idempotency_key=_idempotency_key(request),
            )

        return Response(
            {"status": "false", "message": f"Unsupported category: {category}"},
            status=status.HTTP_400_BAD_REQUEST,
        )


def _idempotency_key(request):
    """Optional client-supplied key (header or body). Same key => same purchase, never charged twice."""
    key = (request.headers.get("Idempotency-Key") or request.data.get("idempotency_key") or "").strip()
    return key if re.fullmatch(r"[A-Za-z0-9._:-]{8,100}", key) else None


def _run_purchase(user, template, cost, idempotency_key=None):
    """Hand a validated purchase to the provider-agnostic engine; returns a DRF Response."""
    from .gateway import engine

    try:
        http_status, body = engine.execute_purchase(user, template, Decimal(str(cost)), idempotency_key)
    except Exception:
        logger.exception("VTU purchase crashed: service=%s user=%s", template.service, user.id)
        return Response(
            {"status": "false", "message": "Service temporarily unavailable. Please try again."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response(body, status=http_status)


def _execute_nellobytes_data_purchase(user, network, plan_id, mobile_number, cost, idempotency_key=None):
    return _run_purchase(user, PurchaseRequest(
        service=Service.DATA, reference="", network=(network or "").upper(),
        plan_id=str(plan_id), target=mobile_number,
    ), cost, idempotency_key)


def _execute_nellobytes_airtime_purchase(user, network, amount, mobile_number, idempotency_key=None):
    # Provider gets the face amount; the wallet is debited the admin-priced cost.
    return _run_purchase(user, PurchaseRequest(
        service=Service.AIRTIME, reference="", network=(network or "").upper(),
        amount=int(amount), target=mobile_number,
    ), customer_price("AIRTIME", network, amount), idempotency_key)


def _execute_nellobytes_cable_purchase(user, cable_tv, package, smartcard_no, phone_no, cost, idempotency_key=None):
    return _run_purchase(user, PurchaseRequest(
        service=Service.CABLE, reference="", network=(cable_tv or "").upper(),
        plan_id=str(package), target=smartcard_no, phone=phone_no,
    ), cost, idempotency_key)


def _execute_nellobytes_electricity_purchase(user, company, meter_type, meter_no, amount, phone_no, idempotency_key=None):
    return _run_purchase(user, PurchaseRequest(
        service=Service.ELECTRICITY, reference="", network=(company or "").upper(),
        amount=int(amount), target=meter_no, phone=phone_no, meter_type=meter_type,
    ), customer_price("ELECTRICITY", company, amount), idempotency_key)


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

        return _execute_nellobytes_airtime_purchase(
            request.user, network, cost, phone_number, idempotency_key=_idempotency_key(request)
        )


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
            request.user, network, plan.plan_id, phone_number, plan.selling_price,
            idempotency_key=_idempotency_key(request),
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
            request.user, company, meter_type, meter_number, cost, phone,
            idempotency_key=_idempotency_key(request),
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
            request.user, provider_name, plan.plan_id, card_number, phone, plan.selling_price,
            idempotency_key=_idempotency_key(request),
        )


def _verify_customer(service, network, target, meter_type="PREPAID"):
    """Smartcard / meter lookup via the first eligible provider that supports it."""
    probe = PurchaseRequest(service=service, reference="", network=(network or "").upper())
    for adapter in router.select(probe).adapters:
        try:
            return adapter.verify_customer(service, probe.network, target, meter_type)
        except NotImplementedError:
            continue
    raise CustomerVerificationError("Verification is temporarily unavailable. Please try again shortly.")


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
            customer_name = _verify_customer(Service.CABLE, cable_tv, smartcard_no)
        except CustomerVerificationError as e:
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
            customer_name = _verify_customer(Service.ELECTRICITY, company, meter_no, meter_type)
        except CustomerVerificationError as e:
            return Response({"status": "false", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"status": "true", "customer_name": customer_name}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class ProviderCallbackView(APIView):
    """
    Generic provider webhook (/vtu/webhook/<provider>/). The adapter parses and, where the
    provider signs callbacks, verifies it. An unverified callback is only a "check now"
    trigger: the real status is fetched server-to-server, so a forged callback cannot
    flip a transaction. Repeated callbacks are no-ops (settle() is idempotent).
    """
    permission_classes = []
    authentication_classes = []
    provider_name = None

    def get(self, request, provider=None):
        return self._handle(request, provider or self.provider_name)

    def post(self, request, provider=None):
        return self._handle(request, provider or self.provider_name)

    def _handle(self, request, provider):
        from dashboard.utils import client_ip, log_webhook_event
        from .gateway import engine

        ip = client_ip(request)
        adapter = registry.get_adapter(provider)
        if adapter is None or not adapter.config.enabled:
            return Response({"status": "unknown_provider"}, status=404)

        # Recorded unconditionally, before any lookup/validation - this row alone answers
        # "is the provider actually hitting my backend?" regardless of what happens next.
        raw = request.query_params if request.method == "GET" else request.data
        log_webhook_event(adapter.name, "received", payload=str(dict(raw))[:1000], ip_address=ip)
        try:
            http_status, body, outcome, detail = engine.handle_webhook(adapter, request)
        except Exception:
            logger.exception("%s webhook crashed", adapter.name)
            log_webhook_event(adapter.name, "error", detail="unhandled error", ip_address=ip)
            return Response({"status": "error"}, status=500)
        log_webhook_event(adapter.name, outcome, detail=detail, ip_address=ip)
        return Response(body, status=http_status)


class NellobytesCallbackView(ProviderCallbackView):
    """Original callback URL, already registered on in-flight Nellobytes orders."""
    provider_name = "nellobytes"
