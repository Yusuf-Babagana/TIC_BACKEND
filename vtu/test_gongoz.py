"""Gongoz adapter tests - HTTP is mocked; response shapes are ASSUMED (the vendor docs show none)."""
import os
from decimal import Decimal
from unittest import mock

import requests
from django.contrib.auth import get_user_model

from vtu.gateway import engine, registry, router
from vtu.gateway.base import CustomerVerificationError, WebhookRejected
from vtu.gateway.types import ErrorCategory, OrderStatus, Outcome, PurchaseRequest, Service
from vtu.models import ProviderPlanCode
from vtu.testing import GatewayTestCase, http_json
from wallet.models import Transaction, Wallet

KEY = "GONGOZ-SECRET-TOKEN-XYZ"
HTTP = "vtu.gateway.adapters.gongoz.requests.request"


class GongozTests(GatewayTestCase):
    fakes = False
    env = {"VTU_GONGOZ_ENABLED": "true", "VTU_GONGOZ_API_KEY": KEY}

    def adapter(self):
        return registry.get_adapter("gongoz")

    def req(self, service=Service.AIRTIME, network="MTN", **kw):
        return PurchaseRequest(service=service, reference="R1", network=network, amount=500,
                               target="08030000000", plan_id=kw.pop("plan_id", ""), **kw)

    def buy(self, **kw):
        return self.adapter().purchase(self.req(**kw))

    # -- request building ---------------------------------------------------
    @mock.patch(HTTP)
    def test_airtime_request_matches_documented_body_and_auth(self, http):
        http.return_value = http_json({"id": 58, "Status": "pending"}, 201)
        self.buy()
        args, kw = http.call_args
        self.assertEqual(args, ("POST", "https://www.gongozconcept.com/api/topup/"))
        self.assertEqual(kw["headers"]["Authorization"], f"Token {KEY}")
        self.assertEqual(kw["json"], {"network": 1, "amount": 500, "mobile_number": "08030000000",
                                      "Ported_number": True, "airtime_type": "VTU"})

    @mock.patch(HTTP)
    def test_electricity_maps_disco_and_meter_type(self, http):
        http.return_value = http_json({"id": 9}, 201)
        r = self.buy(service=Service.ELECTRICITY, network="IKEDC", meter_type="POSTPAID")
        self.assertEqual(http.call_args.kwargs["json"], {"disco_name": 1, "amount": 500, "meter_number": "08030000000", "MeterType": 2})
        self.assertEqual(r.provider_order_id, "billpayment:9")

    @mock.patch(HTTP)
    def test_data_and_cable_use_mapped_plan_codes_only(self, http):
        http.return_value = http_json({"id": 3}, 201)
        a = self.adapter()
        data = self.req(Service.DATA, "MTN", plan_id="1000.00")
        cable = self.req(Service.CABLE, "DSTV", plan_id="PKG1")
        self.assertFalse(a.supports(data) or a.supports(cable))         # unmapped => never offered
        ProviderPlanCode.objects.create(provider="gongoz", service="DATA", network="MTN", plan_id="1000.00", provider_code="281")
        ProviderPlanCode.objects.create(provider="gongoz", service="CABLE", network="DSTV", plan_id="PKG1", provider_code="74")
        self.assertTrue(a.supports(data) and a.supports(cable))
        a.purchase(data)
        self.assertEqual(http.call_args.kwargs["json"], {"network": 1, "mobile_number": "08030000000", "plan": 281, "Ported_number": True})
        a.purchase(cable)
        self.assertEqual(http.call_args.kwargs["json"], {"cablename": 2, "cableplan": 74, "smart_card_number": "08030000000"})

    def test_airtime_not_offered_for_unknown_network(self):
        self.assertFalse(self.adapter().supports(self.req(network="SMILE")))

    # -- outcome classification --------------------------------------------
    @mock.patch(HTTP)
    def test_created_with_id_is_accepted(self, http):
        http.return_value = http_json({"id": 58}, 201)
        r = self.buy()
        self.assertEqual((r.outcome, r.provider_order_id), (Outcome.ACCEPTED, "topup:58"))

    @mock.patch(HTTP)
    def test_auth_and_rate_limit_are_failover_safe_rejections(self, http):
        for code, cat in ((401, ErrorCategory.AUTH), (403, ErrorCategory.AUTH), (429, ErrorCategory.RATE_LIMIT)):
            http.return_value = http_json({"detail": "nope"}, code)
            r = self.buy()
            self.assertEqual((r.outcome, r.category, r.failover_safe), (Outcome.REJECTED, cat, True))

    @mock.patch(HTTP)
    def test_validation_error_is_invalid_request_and_shows_reason(self, http):
        http.return_value = http_json({"mobile_number": ["Enter a valid number"]}, 400)
        r = self.buy()
        self.assertEqual((r.category, r.message, r.failover_safe), (ErrorCategory.INVALID_REQUEST, "Enter a valid number", False))

    @mock.patch(HTTP)
    def test_provider_balance_text_is_never_shown_to_customers(self, http):
        http.return_value = http_json({"error": "Insufficient balance. Your balance is 12.00"}, 400)
        r = self.buy()
        self.assertEqual(r.category, ErrorCategory.PROVIDER_BALANCE)
        self.assertNotIn("12.00", r.message)

    @mock.patch(HTTP)
    def test_ambiguous_cases_never_count_as_rejections(self, http):
        for side in (requests.ReadTimeout(), requests.ConnectionError("reset")):
            http.side_effect = side
            self.assertEqual(self.buy().outcome, Outcome.AMBIGUOUS)
        http.side_effect = None
        for resp in (http_json({"id": 1}, 500), http_json({"Status": "ok"}, 200), http_json({"id": ""}, 201)):
            http.return_value = resp
            self.assertEqual(self.buy().outcome, Outcome.AMBIGUOUS)
        bad = mock.Mock(status_code=200)
        bad.json.side_effect = ValueError()
        http.return_value = bad
        self.assertEqual(self.buy().outcome, Outcome.AMBIGUOUS)

    @mock.patch(HTTP)
    def test_connect_timeout_means_nothing_sent(self, http):
        http.side_effect = requests.ConnectTimeout()
        self.assertEqual(self.buy().outcome, Outcome.REJECTED)

    @mock.patch(HTTP)
    def test_token_never_appears_in_results(self, http):
        http.return_value = http_json({"id": 1, "Authorization": f"Token {KEY}", "api_key": KEY}, 201)
        self.assertNotIn(KEY, repr(self.buy()))
        http.side_effect = requests.ConnectionError(f"https://x?token={KEY}")
        self.assertNotIn(KEY, repr(self.buy()))

    # -- status ------------------------------------------------------------
    @mock.patch(HTTP)
    def test_status_is_unresolved_until_vocabulary_is_configured(self, http):
        http.return_value = http_json({"id": 58, "Status": "successful"})
        self.assertEqual(self.adapter().query_status("topup:58").status, OrderStatus.UNKNOWN)
        self.assertEqual(http.call_args.args, ("GET", "https://www.gongozconcept.com/api/topup/58"))

    @mock.patch(HTTP)
    def test_configured_vocabulary_maps_case_insensitively(self, http):
        with mock.patch.dict(os.environ, {"VTU_GONGOZ_SUCCESS_STATUSES": "successful, delivered", "VTU_GONGOZ_FAILED_STATUSES": "Failed"}):
            for body, want in (({"Status": "Successful"}, OrderStatus.SUCCESSFUL), ({"status": "FAILED"}, OrderStatus.FAILED),
                               ({"Status": "processing"}, OrderStatus.UNKNOWN), ({}, OrderStatus.UNKNOWN)):
                http.return_value = http_json(body)
                self.assertEqual(self.adapter().query_status("data:1").status, want, body)

    @mock.patch(HTTP)
    def test_cannot_query_without_provider_id_or_on_errors(self, http):
        a = self.adapter()
        self.assertEqual(a.query_status("", "TIC-REF").status, OrderStatus.UNKNOWN)
        self.assertEqual(a.query_status("weird:../x").status, OrderStatus.UNKNOWN)
        http.assert_not_called()
        http.return_value = http_json({"detail": "not found"}, 404)
        self.assertEqual(a.query_status("topup:1").status, OrderStatus.UNKNOWN)
        http.side_effect = requests.ReadTimeout()
        self.assertEqual(a.query_status("topup:1").status, OrderStatus.UNKNOWN)

    # -- misc --------------------------------------------------------------
    @mock.patch(HTTP)
    def test_connectivity_probe_reads_user_endpoint_and_hides_body(self, http):
        http.return_value = http_json({"username": "someone", "Account_Balance": "5000"})
        r = self.adapter().check_connectivity()
        self.assertEqual((r["ok"], r["detail"]), (True, "authenticated"))
        self.assertEqual(http.call_args.args, ("GET", "https://www.gongozconcept.com/api/user/"))
        http.return_value = http_json({}, 401)
        self.assertFalse(self.adapter().check_connectivity()["ok"])

    @mock.patch(HTTP)
    def test_verify_customer(self, http):
        a = self.adapter()
        http.return_value = http_json({"name": "JANE DOE"})
        self.assertEqual(a.verify_customer(Service.CABLE, "GOTV", "123"), "JANE DOE")
        self.assertEqual(http.call_args.kwargs["params"], {"smart_card_number": "123", "cablename": 1})
        self.assertEqual(a.verify_customer(Service.ELECTRICITY, "EKEDC", "999", "PREPAID"), "JANE DOE")
        self.assertEqual(http.call_args.kwargs["params"], {"meternumber": "999", "disconame": 2, "mtype": 1})
        http.return_value = http_json({"unexpected": "shape"})
        with self.assertRaises(CustomerVerificationError):
            a.verify_customer(Service.CABLE, "GOTV", "123")

    def test_webhook_refused_not_guessed(self):
        with self.assertRaises(WebhookRejected):
            self.adapter().parse_webhook(mock.Mock())

    def test_disabled_without_key_and_not_routed(self):
        with mock.patch.dict(os.environ, {"VTU_GONGOZ_API_KEY": ""}):
            self.assertTrue(any("VTU_GONGOZ_API_KEY" in p for p in registry.validate_configuration()))
            self.assertNotIn("gongoz", [a.name for a in router.select(self.req()).adapters])
        with mock.patch.dict(os.environ, {"VTU_GONGOZ_ENABLED": ""}):
            self.assertFalse(registry.get_adapter("gongoz").config.enabled)     # off by default


class GongozEngineTests(GatewayTestCase):
    """Gongoz as a failover target behind Nellobytes, through the real engine."""
    nello = True
    fakes = False
    env = {"VTU_GONGOZ_ENABLED": "true", "VTU_GONGOZ_API_KEY": KEY,
           "VTU_GONGOZ_SUCCESS_STATUSES": "successful", "VTU_GONGOZ_FAILED_STATUSES": "failed"}

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.user = User.objects.create_user(username="g", email="g@example.com", password="x")
        Wallet.objects.update_or_create(user=self.user, defaults={"balance": Decimal("5000")})

    def airtime(self):
        return PurchaseRequest(service=Service.AIRTIME, reference="", network="MTN", amount=500, target="08030000000")

    @mock.patch(HTTP)
    @mock.patch("vtu.nellobytes.requests.get")
    def test_fails_over_to_gongoz_after_confirmed_nellobytes_rejection_then_resolves(self, nb, gz):
        nb.return_value = http_json({"status": "INSUFFICIENT_BALANCE"})
        gz.return_value = http_json({"id": 77}, 201)
        status, body = engine.execute_purchase(self.user, self.airtime(), Decimal("500"))
        self.assertEqual((status, body["order_id"]), (202, "topup:77"))
        txn = Transaction.objects.get()
        self.assertEqual(txn.provider, "gongoz")
        self.assertEqual(Wallet.objects.get(user=self.user).balance, Decimal("4500.00"))

        gz.return_value = http_json({"id": 77, "Status": "Successful"})
        self.assertEqual(engine.reconcile_transaction(txn), "SUCCESSFUL")

    @mock.patch(HTTP)
    @mock.patch("vtu.nellobytes.requests.get")
    def test_nellobytes_timeout_does_not_fail_over_to_gongoz(self, nb, gz):
        nb.side_effect = requests.ReadTimeout()
        status, _ = engine.execute_purchase(self.user, self.airtime(), Decimal("500"))
        self.assertEqual(status, 202)
        gz.assert_not_called()                      # the double-purchase guard holds with a real second adapter
        self.assertEqual(Transaction.objects.get().status, "PENDING")

    @mock.patch(HTTP)
    def test_gongoz_timeout_without_id_stays_pending_and_is_never_refunded_by_sweep(self, gz):
        with mock.patch.dict(os.environ, {"VTU_NELLOBYTES_ENABLED": "false"}):
            gz.side_effect = requests.ReadTimeout()
            engine.execute_purchase(self.user, self.airtime(), Decimal("500"))
            txn = Transaction.objects.get()
            self.assertEqual(engine.reconcile_transaction(txn), "PENDING")
        self.assertEqual(Wallet.objects.get(user=self.user).balance, Decimal("4500.00"))


class GongozCatalogCommandTests(GatewayTestCase):
    fakes = False
    env = {"VTU_GONGOZ_ENABLED": "true", "VTU_GONGOZ_API_KEY": KEY}

    CATALOG = {"Cableplan": {
        "DSTVPLAN": [
            {"cableplan_id": "74", "cable": "DSTV", "package": "DStv Padi", "plan_amount": "4400"},
            {"cableplan_id": "85", "cable": "DSTV", "package": "DStv Padi + ExtraView", "plan_amount": "10400"},
            {"cableplan_id": "86", "cable": "DSTV", "package": "DStv Padi + ExtraView", "plan_amount": "10400"}],
        "STARTIMEPLAN": [{"cableplan_id": "103", "cable": "STARTIME", "package": "Nova - 600 Naira - 1 Week", "plan_amount": "600"}],
    }, "Dataplans": {}}

    @mock.patch(HTTP)
    def test_applies_only_exact_unique_cable_matches(self, http):
        from django.core.management import call_command
        from io import StringIO
        from vtu.models import CablePlan
        http.return_value = http_json(self.CATALOG)
        CablePlan.objects.create(provider_name="DSTV", plan_id="dstv-padi", plan_name="DStv Padi", selling_price=Decimal("4400"))
        CablePlan.objects.create(provider_name="DSTV", plan_id="padi-extra", plan_name="DStv Padi + ExtraView", selling_price=Decimal("10400"))
        CablePlan.objects.create(provider_name="DSTV", plan_id="dstv-yanga", plan_name="DStv Yanga", selling_price=Decimal("6000"))
        out = StringIO()
        call_command("gongoz_catalog", "--apply-cable", stdout=out)
        rows = dict(ProviderPlanCode.objects.filter(provider="gongoz").values_list("plan_id", "provider_code"))
        self.assertEqual(rows, {"dstv-padi": "74"})                 # duplicate-id and unmatched plans left for a human
        self.assertIn("ambiguous", out.getvalue())
