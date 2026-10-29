"""Test helpers: isolated provider env, a scriptable fake adapter, and a mocked Nellobytes HTTP layer."""
import os
from unittest import mock

import requests

from django.test import TestCase

from vtu.gateway import registry
from vtu.gateway.base import ProviderAdapter
from vtu.gateway.config import ConfigSpec
from vtu.gateway.types import (
    ErrorCategory, OrderStatus, Outcome, ProviderResult, PurchaseRequest, Service, StatusResult,
    WebhookEvent,
)

NELLO_ENV = {
    "VTU_NELLOBYTES_ENABLED": "true",
    "VTU_NELLOBYTES_USER_ID": "test-user",
    "VTU_NELLOBYTES_API_KEY": "SUPER-SECRET-KEY-123",
}
# Env vars that would leak a developer's real .env into tests.
_SCRUB = ["VTU_USER_ID", "VTU_API_KEY", "VTU_NELLOBYTES_BASE_URL", "VTU_NELLOBYTES_PRIORITY",
          "VTU_FAILURE_THRESHOLD", "VTU_SUSPEND_MINUTES", "VTU_ROUTING_POLICY"]


class FakeAdapter(ProviderAdapter):
    """
    Scriptable provider. ``script`` is a list of ProviderResults handed out one per
    ``purchase``; ``statuses`` maps reference/order id -> OrderStatus for ``query_status``.
    State is class-level because the registry builds a fresh adapter per call.
    """
    label = "Fake"
    services = Service.ALL
    config_spec = ConfigSpec()
    default_enabled = False
    script = None
    calls = None
    statuses = None
    network_ok = True

    @classmethod
    def reset(cls):
        cls.script, cls.calls, cls.statuses = [], [], {}

    def supports(self, request):
        return self.network_ok and request.service in self.services

    def purchase(self, request: PurchaseRequest):
        type(self).calls.append(request)
        return type(self).script.pop(0)

    def query_status(self, provider_order_id="", reference=""):
        s = type(self).statuses
        return StatusResult(s.get(provider_order_id) or s.get(reference) or OrderStatus.UNKNOWN)

    def check_connectivity(self):
        return {"ok": True, "detail": "fake", "elapsed_ms": 1}

    def parse_webhook(self, request):
        d = request.query_params if request.method == "GET" else request.data
        return WebhookEvent(provider_order_id=d.get("orderid", ""), reference=d.get("requestid", ""))


class FakeA(FakeAdapter):
    name = "fakea"
    default_priority = 10


class FakeB(FakeAdapter):
    name = "fakeb"
    default_priority = 20


def accepted(order_id="ORD-1", **extra):
    return ProviderResult(Outcome.ACCEPTED, code="ORDER_RECEIVED", provider_order_id=order_id, extra=extra)


def rejected(category=ErrorCategory.MAINTENANCE, code="PROVIDER_DOWN"):
    return ProviderResult(Outcome.REJECTED, category, code, code)


def ambiguous(category=ErrorCategory.TIMEOUT):
    return ProviderResult(Outcome.AMBIGUOUS, category, "TIMEOUT", "Provider request timed out")


class GatewayTestCase(TestCase):
    """Fake providers fakea (prio 10) and fakeb (prio 20) on; Nellobytes off unless ``nello = True``."""
    nello = False
    fakes = True
    env = {}

    def setUp(self):
        for cls in (FakeA, FakeB):
            cls.reset()
            registry.register(cls)
        self.addCleanup(registry.unregister, "fakea")
        self.addCleanup(registry.unregister, "fakeb")

        env = {k: "" for k in _SCRUB}
        env.update(NELLO_ENV if self.nello else {"VTU_NELLOBYTES_ENABLED": "false"})
        flag = "true" if self.fakes else "false"
        env.update({"VTU_FAKEA_ENABLED": flag, "VTU_FAKEB_ENABLED": flag})
        env.update(self.env)
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

        # No test may touch the network: any HTTP call not explicitly mocked by the test is recorded
        # and fails the test in cleanup (a test's own @mock.patch of requests.get overrides this).
        self.unmocked_http_calls = []

        def _blocked(*args, **kwargs):
            self.unmocked_http_calls.append(str(args[1] if len(args) > 1 else "?")[:80])
            raise requests.ConnectionError("network disabled in tests")

        net = mock.patch("requests.sessions.Session.request", side_effect=_blocked)
        net.start()
        self.addCleanup(net.stop)
        self.addCleanup(lambda: self.assertEqual(self.unmocked_http_calls, [], "test made an unmocked HTTP call"))


def http_json(body, status=200):
    resp = mock.Mock()
    resp.status_code = status
    resp.json.return_value = body
    return resp
