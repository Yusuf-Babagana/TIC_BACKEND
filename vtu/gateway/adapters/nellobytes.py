"""
Nellobytes / ClubKonnect adapter.

Wire format: GET with credentials in the query string; an order is accepted
only when the reply's ``status`` is ``ORDER_RECEIVED``. Any other *JSON* reply
without an order id is a definite rejection; timeouts, dropped connections and
non-JSON bodies are ambiguous.
"""
import time

from django.urls import reverse

from vtu.nellobytes import NellobytesError, NellobytesService

from ..base import CustomerVerificationError, ProviderAdapter
from ..config import ConfigSpec, ProviderConfig
from ..types import (
    ErrorCategory, OrderStatus, Outcome, ProviderResult, PurchaseRequest, Service,
    StatusResult, WebhookEvent, redact, strip_credentials,
)

SPEC = ConfigSpec(
    required=("USER_ID", "API_KEY"),
    optional={"BASE_URL": NellobytesService.BASE_URL, "TIMEOUT": str(NellobytesService.TIMEOUT)},
    secrets=("USER_ID", "API_KEY"),
    # Names used before the multi-provider system existed - still honoured.
    legacy_env={"USER_ID": "VTU_USER_ID", "API_KEY": "VTU_API_KEY"},
)


def load_config():
    return ProviderConfig("nellobytes", SPEC, default_enabled=True)


_PENDING_STATUSES = {"ORDER_RECEIVED", "ORDER_ONHOLD", "ORDER_PROCESSING", "ORDER_PENDING"}


def normalize_order_status(orderstatus, statuscode=None):
    """
    Map Nellobytes' order status to ``OrderStatus``. Success needs BOTH
    ORDER_COMPLETED and (when present) statuscode 200; anything unrecognised is
    UNKNOWN and is never auto-resolved.
    """
    value = str(orderstatus or "").strip().upper()
    code = str(statuscode or "").strip()
    if value == "ORDER_COMPLETED":
        return OrderStatus.SUCCESSFUL if code in ("", "200") else OrderStatus.PENDING
    if any(w in value for w in ("FAILED", "CANCEL", "REFUND")):
        return OrderStatus.FAILED
    if value in _PENDING_STATUSES:
        return OrderStatus.PENDING
    return OrderStatus.UNKNOWN


def classify_rejection(code):
    c = (code or "").upper()
    if c == "UNSUPPORTED":
        return ErrorCategory.UNSUPPORTED
    if c == "INVALID_CREDENTIALS" or "IPADDRESS" in c or "RESTRICTED" in c:
        return ErrorCategory.AUTH
    if "INSUFFICIENT" in c:
        return ErrorCategory.PROVIDER_BALANCE
    if c.startswith("INVALID_API_ERROR") or "MAINTENANCE" in c or "NOT_AVAILABLE" in c:
        return ErrorCategory.MAINTENANCE
    if "LIMIT" in c or "TOO_MANY" in c:
        return ErrorCategory.RATE_LIMIT
    if c.startswith("INVALID") or c.startswith("MINIMUM") or c.startswith("MAXIMUM"):
        return ErrorCategory.INVALID_REQUEST
    return ErrorCategory.UNKNOWN


class NellobytesAdapter(ProviderAdapter):
    name = "nellobytes"
    label = "Nellobytes (ClubKonnect)"
    services = (Service.DATA, Service.AIRTIME, Service.CABLE, Service.ELECTRICITY)
    config_spec = SPEC
    default_enabled = True
    default_priority = 10
    webhook_verified = False    # Nellobytes callbacks are unsigned - always confirmed via query_status

    @staticmethod
    def _plan_is_ours(request):
        """DATA/CABLE plan ids are provider-specific codes: only serve plans imported from Nellobytes."""
        from vtu.models import CablePlan, DataPlan

        net, pid = (request.network or "").upper(), str(request.plan_id)
        if request.service == Service.DATA:
            src = DataPlan.objects.filter(network=net, plan_id=pid).values_list("source", flat=True).first()
        else:
            src = CablePlan.objects.filter(provider_name=net, plan_id=pid).values_list("source", flat=True).first()
        return src in (None, "nellobytes")      # no row = legacy behaviour

    def supports(self, request: PurchaseRequest) -> bool:
        net = (request.network or "").upper()
        if request.service == Service.DATA:
            return net in NellobytesService.NETWORK_CODES and self._plan_is_ours(request)
        if request.service == Service.AIRTIME:
            return net in NellobytesService.NETWORK_CODES
        if request.service == Service.CABLE:
            return net in NellobytesService.CABLE_TV_CODES and self._plan_is_ours(request)
        if request.service == Service.ELECTRICITY:
            return net in NellobytesService.ELECTRIC_COMPANY_CODES
        return False

    def callback_url_path(self):
        # Registered on in-flight orders already; keep the original route.
        return reverse("vtu:nellobytes-webhook")

    # ------------------------------------------------------------------
    def purchase(self, r: PurchaseRequest) -> ProviderResult:
        started = time.monotonic()
        try:
            if r.service == Service.DATA:
                body = NellobytesService.buy_data(r.network, r.plan_id, r.target, r.reference, r.callback_url)
            elif r.service == Service.AIRTIME:
                body = NellobytesService.buy_airtime(r.network, int(r.amount), r.target, r.reference, r.callback_url)
            elif r.service == Service.CABLE:
                body = NellobytesService.buy_cable(r.network, r.plan_id, r.target, r.phone, r.reference, r.callback_url)
            elif r.service == Service.ELECTRICITY:
                body = NellobytesService.buy_electricity(
                    r.network, r.meter_type, r.target, int(r.amount), r.phone, r.reference, r.callback_url
                )
            else:
                return ProviderResult(Outcome.REJECTED, ErrorCategory.UNSUPPORTED, "UNSUPPORTED",
                                      f"Unsupported service: {r.service}")
        except NellobytesError as e:
            return self._from_error(e, started)

        elapsed = int((time.monotonic() - started) * 1000)
        order_id = str(body.get("order_id") or "")
        if not order_id:
            # "ORDER_RECEIVED" without an order id can't be tracked - treat as unclear, not accepted.
            return ProviderResult(
                Outcome.AMBIGUOUS, ErrorCategory.BAD_RESPONSE, "NO_ORDER_ID",
                "Provider accepted the order without an order id", raw=redact(body), elapsed_ms=elapsed,
            )
        reserved = {"orderid", "statuscode", "status", "order_id", "status_code"}
        return ProviderResult(
            Outcome.ACCEPTED, code=str(body.get("status") or ""), provider_order_id=order_id,
            extra=strip_credentials({k: v for k, v in body.items() if k not in reserved}),
            raw=redact(body), elapsed_ms=elapsed,
        )

    @staticmethod
    def _from_error(e: NellobytesError, started) -> ProviderResult:
        elapsed = int((time.monotonic() - started) * 1000)
        if e.ambiguous:
            category = {
                "TIMEOUT": ErrorCategory.TIMEOUT, "CONNECTION": ErrorCategory.CONNECTION,
            }.get(e.code, ErrorCategory.BAD_RESPONSE)
            return ProviderResult(
                Outcome.AMBIGUOUS, category, e.code, str(e),
                provider_order_id=str(getattr(e, "order_id", "") or ""), elapsed_ms=elapsed,
            )
        if e.code == "CONNECT_TIMEOUT":
            # Never connected, so nothing was sent: a definite non-submission, but the provider is down.
            return ProviderResult(Outcome.REJECTED, ErrorCategory.MAINTENANCE, e.code, str(e), elapsed_ms=elapsed)
        return ProviderResult(Outcome.REJECTED, classify_rejection(e.code), e.code, str(e), elapsed_ms=elapsed)

    # ------------------------------------------------------------------
    def query_status(self, provider_order_id="", reference=""):
        try:
            body = NellobytesService.query_order(order_id=provider_order_id or None,
                                                 request_id=None if provider_order_id else reference)
        except NellobytesError:
            return StatusResult(OrderStatus.UNKNOWN, "QUERY_FAILED")
        raw_status = body.get("orderstatus") or body.get("status")
        return StatusResult(
            normalize_order_status(raw_status, body.get("statuscode")),
            code=str(raw_status or ""), raw=redact(body),
        )

    def check_connectivity(self):
        """Wallet-balance read: proves credentials + reachability, places no order."""
        started = time.monotonic()
        cfg_errors = self.config.errors()
        if cfg_errors:
            return {"ok": False, "detail": "; ".join(cfg_errors), "elapsed_ms": 0}
        user_id, api_key = NellobytesService._credentials()
        try:
            body = NellobytesService._get_json(
                "/APIWalletBalanceV1.asp", {"UserID": user_id, "APIKey": api_key}, timeout=15
            )
        except NellobytesError as e:
            return {"ok": False, "detail": str(e), "elapsed_ms": int((time.monotonic() - started) * 1000)}
        ok = body.get("balance") is not None
        return {
            "ok": ok,
            "detail": f"balance {body.get('balance')}" if ok else str(body.get("status") or "UNKNOWN_ERROR"),
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    def parse_webhook(self, request):
        data = request.query_params if request.method == "GET" or not isinstance(request.data, dict) else request.data
        return WebhookEvent(
            provider_order_id=str(data.get("orderid") or ""),
            reference=str(data.get("requestid") or ""),
            claimed_status=data.get("orderstatus") or data.get("status"),
            verified=False,
        )

    def verify_customer(self, service, network, target, meter_type="PREPAID"):
        try:
            if service == Service.CABLE:
                return NellobytesService.verify_smartcard(network, target)
            return NellobytesService.verify_meter(network, target, meter_type)
        except NellobytesError as e:
            raise CustomerVerificationError(str(e))
