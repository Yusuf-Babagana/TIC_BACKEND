"""
Gateway tests. Providers are fakes or a mocked HTTP layer - no network, no real money.
Note: SQLite ignores select_for_update, so true parallel-thread races are NOT exercised
here; the lock-dependent guarantees are tested via the state guards + unique constraint.
"""
import os
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import requests
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from vtu.gateway import engine, health, ledger, registry, router
from vtu.gateway.adapters.nellobytes import NellobytesAdapter, normalize_order_status
from vtu.gateway.base import WebhookRejected
from vtu.gateway.config import ProviderConfig
from vtu.gateway.types import (
    ErrorCategory, OrderStatus, Outcome, PurchaseRequest, Service, WebhookEvent, redact,
)
from vtu.models import PurchaseAttempt, ProviderState
from vtu.testing import (
    FakeA, FakeB, GatewayTestCase, accepted, ambiguous, http_json, rejected,
)
from wallet.models import Transaction, TransactionEvent, Wallet

User = get_user_model()


def make_user(balance="5000", name="buyer"):
    user = User.objects.create_user(username=name, email=f"{name}@example.com", password="x")
    Wallet.objects.update_or_create(user=user, defaults={"balance": Decimal(balance)})
    return user


def airtime_req(network="MTN"):
    return PurchaseRequest(service=Service.AIRTIME, reference="", network=network, amount=500, target="08030000000")


def balance(user):
    return Wallet.objects.get(user=user).balance


# ---------------------------------------------------------------------------
class NellobytesAdapterTests(GatewayTestCase):
    nello = True
    fakes = False

    def adapter(self):
        return registry.get_adapter("nellobytes")

    def buy(self, adapter=None, **kw):
        req = PurchaseRequest(service=Service.AIRTIME, reference="REF1", callback_url="http://cb", network="MTN",
                              amount=500, target="08030000000", **kw)
        return (adapter or self.adapter()).purchase(req)

    @mock.patch("vtu.nellobytes.requests.get")
    def test_accepted_is_normalized_and_extras_passed_through(self, get):
        get.return_value = http_json({"status": "ORDER_RECEIVED", "orderid": "77", "statuscode": "100", "metertoken": "1234-5678"})
        r = self.buy()
        self.assertEqual(r.outcome, Outcome.ACCEPTED)
        self.assertEqual(r.provider_order_id, "77")
        self.assertEqual(r.extra, {"metertoken": "1234-5678"})
        self.assertEqual(get.call_args.kwargs["params"]["RequestID"], "REF1")
        self.assertEqual(get.call_args.kwargs["params"]["MobileNetwork"], "01")

    @mock.patch("vtu.nellobytes.requests.get")
    def test_secrets_never_reach_result_or_audit_payload(self, get):
        get.return_value = http_json({"status": "ORDER_RECEIVED", "orderid": "77", "APIKey": "SUPER-SECRET-KEY-123",
                                      "mobilenumber": "08030000000"})
        r = self.buy()
        self.assertNotIn("SUPER-SECRET-KEY-123", repr(r))           # not in extra (client-bound) nor raw (DB-bound)
        self.assertNotIn("08030000000", repr(r.raw))                # recipient masked to last 4 in the audit copy
        self.assertEqual(r.raw["mobilenumber"], "*******0000")

    @mock.patch("vtu.nellobytes.requests.get")
    def test_bad_recipient_is_confirmed_rejection_not_failover_safe(self, get):
        get.return_value = http_json({"status": "INVALID_MOBILENUMBER"})
        r = self.buy()
        self.assertEqual((r.outcome, r.category), (Outcome.REJECTED, ErrorCategory.INVALID_REQUEST))
        self.assertEqual(r.message, "INVALID_MOBILENUMBER")     # legacy text the app already maps
        self.assertFalse(r.failover_safe)

    @mock.patch("vtu.nellobytes.requests.get")
    def test_provider_balance_is_failover_safe(self, get):
        get.return_value = http_json({"status": "INSUFFICIENT_BALANCE"})
        r = self.buy()
        self.assertEqual(r.category, ErrorCategory.PROVIDER_BALANCE)
        self.assertTrue(r.failover_safe)

    @mock.patch("time.sleep")
    @mock.patch("vtu.nellobytes.requests.get")
    def test_transient_credentials_error_retried_once_then_auth_failure(self, get, _sleep):
        get.return_value = http_json({"status": "INVALID_CREDENTIALS"})
        r = self.buy()
        self.assertEqual(get.call_count, 2)
        self.assertEqual((r.outcome, r.category), (Outcome.REJECTED, ErrorCategory.AUTH))

    @mock.patch("vtu.nellobytes.requests.get")
    def test_read_timeout_is_ambiguous(self, get):
        get.side_effect = requests.ReadTimeout("https://x/?APIKey=SUPER-SECRET-KEY-123")
        r = self.buy()
        self.assertEqual((r.outcome, r.category), (Outcome.AMBIGUOUS, ErrorCategory.TIMEOUT))
        self.assertNotIn("SUPER-SECRET", repr(r))

    @mock.patch("vtu.nellobytes.requests.get")
    def test_dropped_connection_and_garbage_body_are_ambiguous(self, get):
        get.side_effect = requests.ConnectionError("reset")
        self.assertEqual(self.buy().outcome, Outcome.AMBIGUOUS)
        bad = mock.Mock(status_code=200)
        bad.json.side_effect = ValueError()
        get.side_effect = None
        get.return_value = bad
        self.assertEqual(self.buy().outcome, Outcome.AMBIGUOUS)

    @mock.patch("vtu.nellobytes.requests.get")
    def test_connect_timeout_means_nothing_was_sent(self, get):
        get.side_effect = requests.ConnectTimeout("x")
        r = self.buy()
        self.assertEqual((r.outcome, r.category), (Outcome.REJECTED, ErrorCategory.MAINTENANCE))

    @mock.patch("vtu.nellobytes.requests.get")
    def test_order_state_other_than_received_is_not_treated_as_rejection(self, get):
        get.return_value = http_json({"status": "ORDER_ONHOLD", "orderid": "88"})
        r = self.buy()
        self.assertEqual(r.outcome, Outcome.AMBIGUOUS)
        self.assertEqual(r.provider_order_id, "88")

    @mock.patch("vtu.nellobytes.requests.get")
    def test_received_without_order_id_is_ambiguous(self, get):
        get.return_value = http_json({"status": "ORDER_RECEIVED"})
        self.assertEqual(self.buy().outcome, Outcome.AMBIGUOUS)

    def test_status_normalization_requires_exact_completion(self):
        n = normalize_order_status
        self.assertEqual(n("ORDER_COMPLETED", "200"), OrderStatus.SUCCESSFUL)
        self.assertEqual(n("ORDER_COMPLETED", ""), OrderStatus.SUCCESSFUL)
        self.assertEqual(n("ORDER_COMPLETED", "500"), OrderStatus.PENDING)      # contradictory -> don't trust
        self.assertEqual(n("ORDER_CANCELLED", "100"), OrderStatus.FAILED)
        self.assertEqual(n("ORDER_ONHOLD"), OrderStatus.PENDING)
        self.assertEqual(n("INCOMPLETE_THING"), OrderStatus.UNKNOWN)            # no substring matching on COMPLETED
        self.assertEqual(n("INVALID_ORDERID"), OrderStatus.UNKNOWN)
        self.assertEqual(n(None), OrderStatus.UNKNOWN)

    @mock.patch("vtu.nellobytes.requests.get")
    def test_query_status_failure_is_unknown_not_failed(self, get):
        get.side_effect = requests.ReadTimeout()
        self.assertEqual(self.adapter().query_status("77").status, OrderStatus.UNKNOWN)

    def test_unsupported_networks_not_offered(self):
        a = self.adapter()
        self.assertTrue(a.supports(airtime_req("MTN")))
        self.assertFalse(a.supports(airtime_req("9MOBILE")))
        self.assertFalse(a.supports(PurchaseRequest(service=Service.CABLE, reference="", network="BOGUS")))

    @mock.patch("vtu.nellobytes.requests.get")
    def test_connectivity_probe_only_reads_balance(self, get):
        get.return_value = http_json({"balance": "1500.00"})
        r = self.adapter().check_connectivity()
        self.assertTrue(r["ok"])
        self.assertIn("APIWalletBalanceV1", get.call_args.args[0])
        get.return_value = http_json({"status": "INVALID_CREDENTIALS"})
        self.assertFalse(self.adapter().check_connectivity()["ok"])


class ConfigTests(GatewayTestCase):
    fakes = False

    def test_new_names_win_over_legacy_and_secrets_are_masked(self):
        with mock.patch.dict(os.environ, {"VTU_USER_ID": "legacy", "VTU_API_KEY": "legacykey",
                                          "VTU_NELLOBYTES_USER_ID": "newuser", "VTU_NELLOBYTES_API_KEY": "newkey-VALUE"}):
            cfg = registry.get_adapter("nellobytes").config
            self.assertEqual(cfg.get("USER_ID"), "newuser")
            self.assertNotIn("newkey-VALUE", repr(cfg))
            self.assertNotIn("newuser", repr(cfg))
            self.assertEqual(cfg.public_view()["API_KEY"], "(set)")

    def test_legacy_names_still_work_and_enabled_by_default(self):
        with mock.patch.dict(os.environ, {"VTU_NELLOBYTES_ENABLED": "", "VTU_USER_ID": "legacy", "VTU_API_KEY": "k"}):
            cfg = registry.get_adapter("nellobytes").config
            self.assertTrue(cfg.enabled)
            self.assertEqual(cfg.get("USER_ID"), "legacy")
            self.assertTrue(cfg.is_valid)

    def test_validation_flags_enabled_but_incomplete_provider(self):
        with mock.patch.dict(os.environ, {"VTU_NELLOBYTES_ENABLED": "true", "VTU_NELLOBYTES_API_KEY": "",
                                          "VTU_NELLOBYTES_USER_ID": "", "VTU_USER_ID": "", "VTU_API_KEY": ""}):
            problems = registry.validate_configuration()
            self.assertTrue(any("VTU_NELLOBYTES_API_KEY" in p for p in problems))

    def test_disabled_provider_is_not_validated(self):
        with mock.patch.dict(os.environ, {"VTU_NELLOBYTES_ENABLED": "false", "VTU_NELLOBYTES_API_KEY": ""}):
            self.assertEqual(registry.validate_configuration(), [])

    def test_redact(self):
        out = redact({"APIKey": "k", "UserID": "u", "meterno": "12345678901", "n": {"password": "p", "ok": 1}})
        self.assertEqual(out["APIKey"], "***")
        self.assertEqual(out["UserID"], "***")
        self.assertTrue(out["meterno"].endswith("8901") and out["meterno"].startswith("*"))
        self.assertEqual(out["n"], {"password": "***", "ok": 1})


# ---------------------------------------------------------------------------
class RoutingTests(GatewayTestCase):
    def names(self, req=None):
        return [a.name for a in router.select(req or airtime_req()).adapters]

    def test_orders_by_priority_then_name(self):
        self.assertEqual(self.names(), ["fakea", "fakeb"])

    def test_env_priority_overrides_default_and_admin_override_wins(self):
        with mock.patch.dict(os.environ, {"VTU_FAKEB_PRIORITY": "1"}):
            self.assertEqual(self.names(), ["fakeb", "fakea"])
            ProviderState.objects.update_or_create(name="fakea", defaults={"priority_override": 0})
            self.assertEqual(self.names(), ["fakea", "fakeb"])

    def test_env_disabled_and_admin_disabled_are_skipped(self):
        with mock.patch.dict(os.environ, {"VTU_FAKEA_ENABLED": "false"}):
            self.assertEqual(self.names(), ["fakeb"])
        ProviderState.objects.update_or_create(name="fakeb", defaults={"admin_enabled": False})
        self.assertEqual(self.names(), ["fakea"])

    def test_misconfigured_provider_is_never_routed(self):
        with mock.patch.dict(os.environ, {"VTU_NELLOBYTES_ENABLED": "true", "VTU_NELLOBYTES_API_KEY": "",
                                          "VTU_NELLOBYTES_USER_ID": ""}):
            self.assertNotIn("nellobytes", self.names())

    def test_unsupported_vs_unavailable_are_distinguished(self):
        FakeA.network_ok = FakeB.network_ok = False
        try:
            sel = router.select(airtime_req())
            self.assertEqual((sel.supporting, sel.adapters), (0, []))
        finally:
            FakeA.network_ok = FakeB.network_ok = True
        ProviderState.objects.update_or_create(name="fakea", defaults={"admin_enabled": False})
        ProviderState.objects.update_or_create(name="fakeb", defaults={"admin_enabled": False})
        sel = router.select(airtime_req())
        self.assertEqual((sel.supporting, sel.adapters), (2, []))

    def test_custom_policy_is_pluggable(self):
        with mock.patch.dict(os.environ, {"VTU_ROUTING_POLICY": "vtu.test_gateway.ReversePolicy"}):
            self.assertEqual(self.names(), ["fakeb", "fakea"])


class ReversePolicy(router.RoutingPolicy):
    def order(self, candidates, request):
        return [a for a, _ in sorted(candidates, key=lambda c: c[0].name, reverse=True)]


class CircuitBreakerTests(GatewayTestCase):
    env = {"VTU_FAILURE_THRESHOLD": "3", "VTU_SUSPEND_MINUTES": "10"}

    def test_suspends_after_threshold_and_skips_provider(self):
        for _ in range(2):
            health.record_failure("fakea", ErrorCategory.TIMEOUT, "t")
        self.assertFalse(health.is_suspended(health.get_state("fakea")))
        health.record_failure("fakea", ErrorCategory.TIMEOUT, "t")
        self.assertTrue(health.is_suspended(health.get_state("fakea")))
        self.assertEqual([a.name for a in router.select(airtime_req()).adapters], ["fakeb"])

    def test_invalid_request_failures_do_not_count_against_health(self):
        for _ in range(5):
            health.record_failure("fakea", ErrorCategory.INVALID_REQUEST)
        self.assertEqual(health.get_state("fakea").consecutive_failures, 0)

    def test_recovery_after_suspension_window_and_success_clears(self):
        for _ in range(3):
            health.record_failure("fakea", ErrorCategory.MAINTENANCE)
        ProviderState.objects.filter(name="fakea").update(suspended_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual([a.name for a in router.select(airtime_req()).adapters], ["fakea", "fakeb"])
        health.record_success("fakea")
        st = health.get_state("fakea")
        self.assertEqual((st.consecutive_failures, st.suspended_until), (0, None))

    def test_half_open_failure_resuspends_immediately(self):
        for _ in range(3):
            health.record_failure("fakea", ErrorCategory.MAINTENANCE)
        ProviderState.objects.filter(name="fakea").update(suspended_until=timezone.now() - timedelta(seconds=1))
        health.record_failure("fakea", ErrorCategory.MAINTENANCE)
        self.assertTrue(health.is_suspended(health.get_state("fakea")))

    def test_outage_then_engine_routes_around_and_recovers(self):
        user = make_user()
        for _ in range(3):
            FakeA.script.append(rejected(ErrorCategory.MAINTENANCE))
            FakeB.script.append(accepted("B-%d" % len(FakeB.script)))
            status, _ = engine.execute_purchase(user, airtime_req(), Decimal("500"))
            self.assertEqual(status, 202)
        self.assertTrue(health.is_suspended(health.get_state("fakea")))
        calls_a = len(FakeA.calls)
        FakeB.script.append(accepted("B-next"))
        engine.execute_purchase(user, airtime_req(), Decimal("500"))
        self.assertEqual(len(FakeA.calls), calls_a)         # suspended: not even tried


# ---------------------------------------------------------------------------
class EngineFailoverTests(GatewayTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user()

    def buy(self, key=None, cost="500"):
        return engine.execute_purchase(self.user, airtime_req(), Decimal(cost), key)

    def test_failover_after_confirmed_provider_side_rejection(self):
        FakeA.script = [rejected(ErrorCategory.MAINTENANCE)]
        FakeB.script = [accepted("B-1")]
        status, body = self.buy()
        self.assertEqual((status, body["order_id"]), (202, "B-1"))
        txn = Transaction.objects.get()
        self.assertEqual((txn.provider, txn.order_id, txn.status), ("fakeb", "B-1", "PENDING"))
        self.assertEqual(balance(self.user), Decimal("4500.00"))        # debited exactly once
        attempts = list(txn.attempts.values_list("provider", "sequence", "outcome", "reference"))
        self.assertEqual(attempts, [("fakea", 1, "REJECTED", txn.reference),
                                    ("fakeb", 2, "ACCEPTED", f"{txn.reference}-2")])
        self.assertEqual(len(FakeB.calls), 1)

    def test_invalid_request_does_not_fail_over_and_refunds(self):
        FakeA.script = [rejected(ErrorCategory.INVALID_REQUEST, "INVALID_MOBILENUMBER")]
        status, body = self.buy()
        self.assertEqual((status, body["message"]), (502, "INVALID_MOBILENUMBER"))
        self.assertEqual(FakeB.calls, [])
        self.assertEqual(balance(self.user), Decimal("5000.00"))
        self.assertEqual(Transaction.objects.get().status, "FAILED")

    def test_ambiguous_timeout_never_fails_over_or_refunds(self):
        FakeA.script = [ambiguous()]
        FakeB.script = [accepted("SHOULD-NOT-HAPPEN")]
        status, body = self.buy()
        self.assertEqual((status, body["status"]), (202, "pending"))
        self.assertEqual(FakeB.calls, [])                               # the double-purchase guard
        txn = Transaction.objects.get()
        self.assertEqual(txn.status, "PENDING")
        self.assertIsNone(txn.refunded_at)
        self.assertEqual(balance(self.user), Decimal("4500.00"))        # money stays reserved
        self.assertEqual(txn.attempts.get().outcome, Outcome.AMBIGUOUS)

    def test_adapter_crash_is_treated_as_ambiguous(self):
        FakeA.script = []           # pop() raises inside purchase
        status, _ = self.buy()
        self.assertEqual(status, 202)
        self.assertEqual(FakeB.calls, [])
        self.assertEqual(Transaction.objects.get().status, "PENDING")

    def test_all_providers_reject_refunds_exactly_once(self):
        FakeA.script = [rejected(ErrorCategory.MAINTENANCE)]
        FakeB.script = [rejected(ErrorCategory.AUTH, "INVALID_CREDENTIALS")]
        status, _ = self.buy()
        self.assertEqual(status, 502)
        txn = Transaction.objects.get()
        self.assertEqual((txn.status, balance(self.user)), ("FAILED", Decimal("5000.00")))
        self.assertIsNotNone(txn.refunded_at)
        self.assertEqual(txn.attempts.count(), 2)
        deltas = list(txn.events.values_list("wallet_delta", flat=True))
        self.assertEqual(sum(deltas), Decimal("0.00"))      # ledger nets to zero: debit then refund

    def test_provider_float_exhausted_shows_maintenance_message(self):
        FakeA.script = [rejected(ErrorCategory.PROVIDER_BALANCE, "INSUFFICIENT_BALANCE")]
        FakeB.script = [rejected(ErrorCategory.PROVIDER_BALANCE, "INSUFFICIENT_BALANCE")]
        status, body = self.buy()
        self.assertEqual(status, 503)
        self.assertIn("maintenance", body["message"])
        self.assertNotIn("Insufficient", body["message"])

    def test_insufficient_wallet_touches_no_provider(self):
        status, body = self.buy(cost="9000")
        self.assertEqual((status, body["message"]), (400, "Insufficient Balance"))
        self.assertEqual((FakeA.calls, Transaction.objects.count()), ([], 0))

    def test_no_supporting_provider_does_not_debit(self):
        FakeA.network_ok = FakeB.network_ok = False
        try:
            status, _ = self.buy()
        finally:
            FakeA.network_ok = FakeB.network_ok = True
        self.assertEqual((status, balance(self.user), Transaction.objects.count()), (400, Decimal("5000.00"), 0))

    def test_all_suspended_returns_maintenance_without_debit(self):
        for n in ("fakea", "fakeb"):
            ProviderState.objects.update_or_create(name=n, defaults={"admin_enabled": False})
        status, _ = self.buy()
        self.assertEqual((status, balance(self.user)), (503, Decimal("5000.00")))

    def test_provider_extras_returned_to_client(self):
        FakeA.script = [accepted("E-1", metertoken="1111-2222")]
        _, body = self.buy()
        self.assertEqual(body["metertoken"], "1111-2222")

    def test_attempt_rows_store_no_secret_or_full_number(self):
        FakeA.script = [accepted("E-1")]
        self.buy()
        blob = str(list(PurchaseAttempt.objects.values()))
        self.assertNotIn("08030000000", blob)


class IdempotencyTests(GatewayTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user()

    def test_repeat_with_same_key_charges_and_submits_once(self):
        FakeA.script = [accepted("K-1")]
        s1, b1 = engine.execute_purchase(self.user, airtime_req(), Decimal("500"), "key-aaaaaaaa")
        s2, b2 = engine.execute_purchase(self.user, airtime_req(), Decimal("500"), "key-aaaaaaaa")
        self.assertEqual((s1, s2), (202, 202))
        self.assertEqual(b2["reference"], b1["reference"])
        self.assertTrue(b2["idempotent_replay"])
        self.assertEqual(len(FakeA.calls), 1)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(balance(self.user), Decimal("4500.00"))

    def test_replay_of_refunded_purchase_reports_failure_and_does_not_recharge(self):
        FakeA.script = [rejected(ErrorCategory.INVALID_REQUEST, "INVALID_MOBILENUMBER")]
        engine.execute_purchase(self.user, airtime_req(), Decimal("500"), "key-bbbbbbbb")
        status, body = engine.execute_purchase(self.user, airtime_req(), Decimal("500"), "key-bbbbbbbb")
        self.assertEqual(status, 409)
        self.assertEqual(balance(self.user), Decimal("5000.00"))
        self.assertEqual(len(FakeA.calls), 1)

    def test_same_key_different_users_are_independent(self):
        other = make_user(name="other")
        FakeA.script = [accepted("U-1"), accepted("U-2")]
        engine.execute_purchase(self.user, airtime_req(), Decimal("500"), "shared-key-1")
        s, _ = engine.execute_purchase(other, airtime_req(), Decimal("500"), "shared-key-1")
        self.assertEqual(Transaction.objects.count(), 2)
        self.assertEqual(s, 202)

    def test_unique_key_race_rolls_back_the_losing_debit(self):
        """Simulates two requests passing the pre-check together: the DB constraint must undo the second debit."""
        txn, _ = ledger.reserve(self.user, "AIRTIME", Decimal("500"), "TIC-FIRST", "race-key-001")
        with mock.patch("vtu.gateway.ledger.find_by_idempotency_key", side_effect=[None, txn]):
            loser, created = ledger.reserve(self.user, "AIRTIME", Decimal("500"), "TIC-SECOND", "race-key-001")
        self.assertFalse(created)
        self.assertEqual(loser.pk, txn.pk)
        self.assertEqual(balance(self.user), Decimal("4500.00"))        # one debit only
        self.assertEqual(Transaction.objects.count(), 1)

    def test_http_endpoint_honours_header_key(self):
        client = APIClient()
        client.force_authenticate(self.user)
        FakeA.script = [accepted("H-1")]
        payload = {"category": "AIRTIME", "provider": "MTN", "plan_id": "x", "target_id": "08030000000", "amount": "500"}
        r1 = client.post(reverse("vtu:unified-purchase"), payload, format="json", HTTP_IDEMPOTENCY_KEY="client-key-0001")
        r2 = client.post(reverse("vtu:unified-purchase"), payload, format="json", HTTP_IDEMPOTENCY_KEY="client-key-0001")
        self.assertEqual((r1.status_code, r2.status_code), (202, 202))
        self.assertEqual(balance(self.user), Decimal("4500.00"))

    def test_without_key_behaviour_is_unchanged(self):
        FakeA.script = [accepted("N-1"), accepted("N-2")]
        engine.execute_purchase(self.user, airtime_req(), Decimal("500"))
        engine.execute_purchase(self.user, airtime_req(), Decimal("500"))
        self.assertEqual(Transaction.objects.count(), 2)


# ---------------------------------------------------------------------------
class SettlementTests(GatewayTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user()
        FakeA.script = [accepted("S-1")]
        engine.execute_purchase(self.user, airtime_req(), Decimal("500"))
        self.txn = Transaction.objects.get()

    def test_refund_happens_exactly_once_however_often_it_is_triggered(self):
        results = [ledger.settle(self.txn.pk, OrderStatus.FAILED, src) for src in ("webhook", "reconcile", "status-poll")]
        self.assertEqual(results, [True, False, False])
        self.assertEqual(balance(self.user), Decimal("5000.00"))
        self.assertEqual(self.txn.events.filter(wallet_delta=Decimal("500.00")).count(), 1)

    def test_success_is_terminal_and_cannot_later_refund(self):
        self.assertTrue(ledger.settle(self.txn.pk, OrderStatus.SUCCESSFUL, "webhook"))
        self.assertFalse(ledger.settle(self.txn.pk, OrderStatus.FAILED, "reconcile"))
        self.assertEqual(balance(self.user), Decimal("4500.00"))
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, "SUCCESSFUL")

    def test_late_success_after_refund_is_flagged_not_applied(self):
        ledger.settle(self.txn.pk, OrderStatus.FAILED, "reconcile")
        with self.assertLogs("vtu.gateway", level="CRITICAL"):
            self.assertFalse(ledger.settle(self.txn.pk, OrderStatus.SUCCESSFUL, "webhook"))
        self.assertTrue(self.txn.events.filter(detail__startswith="ANOMALY").exists())
        self.assertEqual(balance(self.user), Decimal("5000.00"))

    def test_non_final_outcomes_never_change_anything(self):
        for o in (OrderStatus.PENDING, OrderStatus.UNKNOWN):
            self.assertFalse(ledger.settle(self.txn.pk, o, "reconcile"))
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, "PENDING")

    def test_every_transition_is_audited(self):
        ledger.settle(self.txn.pk, OrderStatus.SUCCESSFUL, "webhook")
        trail = [(e.from_status, e.to_status, e.source) for e in self.txn.events.all()]
        self.assertEqual(trail[0], ("", "PENDING", "purchase"))
        self.assertEqual(trail[-1], ("PENDING", "SUCCESSFUL", "webhook"))

    def test_legacy_apply_order_outcome_shim_is_idempotent(self):
        from vtu.nellobytes import NellobytesService
        NellobytesService.apply_order_outcome(self.txn.pk, "FAILED")
        NellobytesService.apply_order_outcome(self.txn.pk, "FAILED")
        self.assertEqual(balance(self.user), Decimal("5000.00"))

    def test_admin_refund_blocked_after_automatic_refund(self):
        ledger.settle(self.txn.pk, OrderStatus.FAILED, "reconcile")
        admin = User.objects.create_superuser(username="adm", email="a@example.com", password="x")
        self.client.force_login(admin)
        r = self.client.post(reverse("dashboard_transaction_refund", args=[self.txn.pk]))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(balance(self.user), Decimal("5000.00"))


class ReconciliationTests(GatewayTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user()

    def pending_ambiguous(self):
        FakeA.script = [ambiguous()]
        engine.execute_purchase(self.user, airtime_req(), Decimal("500"))
        return Transaction.objects.get()

    def test_ambiguous_order_confirmed_successful_by_reference_query(self):
        txn = self.pending_ambiguous()
        FakeA.statuses[txn.reference] = OrderStatus.SUCCESSFUL
        self.assertEqual(engine.reconcile_transaction(txn), "SUCCESSFUL")
        self.assertEqual(balance(self.user), Decimal("4500.00"))

    def test_ambiguous_order_confirmed_failed_is_refunded_once(self):
        txn = self.pending_ambiguous()
        FakeA.statuses[txn.reference] = OrderStatus.FAILED
        engine.reconcile_transaction(txn)
        engine.reconcile_transaction(txn)
        self.assertEqual(balance(self.user), Decimal("5000.00"))

    def test_unknown_or_pending_never_refunds(self):
        txn = self.pending_ambiguous()
        for answer in (OrderStatus.UNKNOWN, OrderStatus.PENDING):
            FakeA.statuses[txn.reference] = answer
            self.assertEqual(engine.reconcile_transaction(txn), "PENDING")
        self.assertEqual(balance(self.user), Decimal("4500.00"))

    def test_failover_does_not_happen_during_reconciliation_either(self):
        txn = self.pending_ambiguous()
        FakeA.statuses[txn.reference] = OrderStatus.FAILED
        engine.reconcile_transaction(txn)
        self.assertEqual(FakeB.calls, [])

    def test_orphan_without_any_submission_is_refunded_only_after_grace(self):
        txn, _ = ledger.reserve(self.user, "AIRTIME", Decimal("500"), "TIC-ORPHAN")
        self.assertEqual(engine.reconcile_transaction(txn), "PENDING")
        Transaction.objects.filter(pk=txn.pk).update(created_at=timezone.now() - timedelta(minutes=30))
        self.assertEqual(engine.reconcile_transaction(txn), "FAILED")
        self.assertEqual(balance(self.user), Decimal("5000.00"))

    def test_crash_mid_call_leaves_submitting_attempt_that_blocks_orphan_refund(self):
        txn, _ = ledger.reserve(self.user, "AIRTIME", Decimal("500"), "TIC-MIDCALL")
        PurchaseAttempt.objects.create(transaction=txn, provider="fakea", reference="TIC-MIDCALL")
        Transaction.objects.filter(pk=txn.pk).update(created_at=timezone.now() - timedelta(minutes=30))
        self.assertEqual(engine.reconcile_transaction(txn), "PENDING")      # status unknown => keep funds held
        FakeA.statuses["TIC-MIDCALL"] = OrderStatus.SUCCESSFUL
        self.assertEqual(engine.reconcile_transaction(txn), "SUCCESSFUL")

    def test_legacy_transaction_without_attempts_uses_order_id(self):
        txn = Transaction.objects.create(user=self.user, trans_type="AIRTIME", amount=Decimal("100"),
                                         reference="OLD-1", order_id="LEG-1", status="PENDING", provider="fakea")
        FakeA.statuses["LEG-1"] = OrderStatus.SUCCESSFUL
        self.assertEqual(engine.reconcile_transaction(txn), "SUCCESSFUL")

    def test_sweep_command_resolves_old_pending(self):
        txn = self.pending_ambiguous()
        Transaction.objects.filter(pk=txn.pk).update(created_at=timezone.now() - timedelta(minutes=10))
        FakeA.statuses[txn.reference] = OrderStatus.SUCCESSFUL
        self.assertEqual(engine.reconcile_pending(3), (1, 1))

    def test_status_endpoint_self_heals(self):
        txn = self.pending_ambiguous()
        Transaction.objects.filter(pk=txn.pk).update(created_at=timezone.now() - timedelta(minutes=1))
        FakeA.statuses[txn.reference] = OrderStatus.SUCCESSFUL
        client = APIClient()
        client.force_authenticate(self.user)
        r = client.get(reverse("wallet:transaction-status", args=[txn.reference]))
        self.assertEqual(r.json()["status"], "SUCCESSFUL")


# ---------------------------------------------------------------------------
class SignedFake(FakeA):
    """Adapter whose webhook is cryptographically verified (shared secret in the header)."""
    name = "signedfake"
    webhook_verified = True

    def parse_webhook(self, request):
        if request.headers.get("X-Sig") != "good":
            raise WebhookRejected("bad signature")
        d = request.data
        return WebhookEvent(provider_order_id=d.get("order", ""), reference=d.get("ref", ""),
                            claimed_status=d.get("status"), verified=True)


class NellobytesWebhookTests(GatewayTestCase):
    nello = True
    fakes = False

    def setUp(self):
        super().setUp()
        self.user = make_user()
        self.client = APIClient()

    def place(self, order):
        with mock.patch("vtu.nellobytes.requests.get") as get:
            get.return_value = http_json({"status": "ORDER_RECEIVED", "orderid": order})
            engine.execute_purchase(self.user, airtime_req(), Decimal("500"))
        return Transaction.objects.get()

    def test_forged_failure_callback_cannot_trigger_refund(self):
        """Unsigned callback claims CANCELLED; the provider's own answer is COMPLETED -> no refund."""
        txn = self.place("N-9")
        with mock.patch("vtu.nellobytes.requests.get") as get:
            get.return_value = http_json({"orderstatus": "ORDER_COMPLETED", "statuscode": "200"})
            r = self.client.post(reverse("vtu:nellobytes-webhook"),
                                 {"orderid": "N-9", "requestid": txn.reference, "orderstatus": "ORDER_CANCELLED"}, format="json")
        self.assertEqual(r.status_code, 200)
        txn.refresh_from_db()
        self.assertEqual(txn.status, "SUCCESSFUL")
        self.assertEqual(balance(self.user), Decimal("4500.00"))

    def test_forged_success_callback_does_not_complete_a_pending_order(self):
        self.place("N-8")
        with mock.patch("vtu.nellobytes.requests.get") as get:
            get.return_value = http_json({"orderstatus": "ORDER_ONHOLD"})
            self.client.get(reverse("vtu:nellobytes-webhook"), {"orderid": "N-8", "orderstatus": "ORDER_COMPLETED"})
        self.assertEqual(Transaction.objects.get().status, "PENDING")

    def test_genuine_failure_callback_refunds_once_and_replays_are_ignored(self):
        self.place("N-7")
        with mock.patch("vtu.nellobytes.requests.get") as get:
            get.return_value = http_json({"orderstatus": "ORDER_CANCELLED"})
            r1 = self.client.get(reverse("vtu:nellobytes-webhook"), {"orderid": "N-7"})
            r2 = self.client.get(reverse("vtu:nellobytes-webhook"), {"orderid": "N-7"})
        self.assertEqual((r1.json()["status"], r2.json()["status"]), ("acknowledged", "already_resolved"))
        self.assertEqual(balance(self.user), Decimal("5000.00"))

    def test_provider_query_failure_leaves_order_pending(self):
        self.place("N-6")
        with mock.patch("vtu.nellobytes.requests.get", side_effect=requests.ReadTimeout()):
            r = self.client.get(reverse("vtu:nellobytes-webhook"), {"orderid": "N-6"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Transaction.objects.get().status, "PENDING")


class WebhookTests(GatewayTestCase):
    env = {"VTU_SIGNEDFAKE_ENABLED": "true"}

    def setUp(self):
        super().setUp()
        registry.register(SignedFake)
        self.addCleanup(registry.unregister, "signedfake")
        SignedFake.reset()
        for n in ("fakea", "fakeb"):
            ProviderState.objects.update_or_create(name=n, defaults={"admin_enabled": False})
        self.user = make_user()
        self.client = APIClient()

    def make_pending(self, adapter_cls, order="W-1"):
        ProviderState.objects.update_or_create(name=adapter_cls.name, defaults={"admin_enabled": True})
        adapter_cls.script = [accepted(order)]
        engine.execute_purchase(self.user, airtime_req(), Decimal("500"))
        return Transaction.objects.get(order_id=order)

    def test_duplicate_callback_is_ignored(self):
        self.make_pending(FakeA)
        FakeA.statuses["W-1"] = OrderStatus.FAILED
        url = reverse("vtu:provider-webhook", kwargs={"provider": "fakea"})
        r1 = self.client.post(url, {"orderid": "W-1"}, format="json")
        r2 = self.client.post(url, {"orderid": "W-1"}, format="json")
        self.assertEqual((r1.json()["status"], r2.json()["status"]), ("acknowledged", "already_resolved"))
        self.assertEqual(balance(self.user), Decimal("5000.00"))

    def test_unknown_order_and_unknown_provider_404(self):
        url = reverse("vtu:provider-webhook", kwargs={"provider": "fakea"})
        self.assertEqual(self.client.post(url, {"orderid": "nope"}, format="json").status_code, 404)
        url = reverse("vtu:provider-webhook", kwargs={"provider": "doesnotexist"})
        self.assertEqual(self.client.post(url, {"orderid": "x"}, format="json").status_code, 404)

    def test_invalid_signature_rejected_and_changes_nothing(self):
        txn = self.make_pending(SignedFake, "SIG-1")
        url = reverse("vtu:provider-webhook", kwargs={"provider": "signedfake"})
        r = self.client.post(url, {"order": "SIG-1", "status": "FAILED"}, format="json", HTTP_X_SIG="forged")
        self.assertEqual(r.status_code, 401)
        txn.refresh_from_db()
        self.assertEqual(txn.status, "PENDING")
        self.assertEqual(balance(self.user), Decimal("4500.00"))

    def test_valid_signature_settles_without_extra_query_then_duplicates_are_noops(self):
        self.make_pending(SignedFake, "SIG-2")
        url = reverse("vtu:provider-webhook", kwargs={"provider": "signedfake"})
        body = {"order": "SIG-2", "status": "FAILED"}
        self.assertEqual(self.client.post(url, body, format="json", HTTP_X_SIG="good").status_code, 200)
        self.client.post(url, body, format="json", HTTP_X_SIG="good")
        self.assertEqual(Transaction.objects.get().status, "FAILED")
        self.assertEqual(balance(self.user), Decimal("5000.00"))

    def test_callbacks_are_logged(self):
        from dashboard.models import WebhookLog
        self.client.post(reverse("vtu:provider-webhook", kwargs={"provider": "fakea"}), {"orderid": "zzz"}, format="json")
        self.assertTrue(WebhookLog.objects.filter(provider="fakea", outcome="received").exists())


# ---------------------------------------------------------------------------
class ResellerAndAdminTests(GatewayTestCase):
    nello = True
    fakes = False

    def setUp(self):
        super().setUp()
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @mock.patch("vtu.nellobytes.requests.get")
    def test_timeout_no_longer_loses_the_order_or_refunds_blindly(self, get):
        """Regression for the original bug: a timeout used to mark FAILED while the order may have gone through."""
        get.side_effect = requests.ReadTimeout()
        r = self.client.post(reverse("vtu:unified-purchase"), {
            "category": "AIRTIME", "provider": "MTN", "plan_id": "x", "target_id": "08030000000", "amount": "500"}, format="json")
        self.assertEqual(r.status_code, 202)
        txn = Transaction.objects.get()
        self.assertEqual(txn.status, "PENDING")
        self.assertEqual(balance(self.user), Decimal("4500.00"))

    @mock.patch("vtu.nellobytes.requests.get")
    def test_legacy_rejection_messages_and_statuses_preserved(self, get):
        get.return_value = http_json({"status": "INVALID_MOBILENUMBER"})
        r = self.client.post(reverse("vtu:unified-purchase"), {
            "category": "AIRTIME", "provider": "MTN", "plan_id": "x", "target_id": "0803", "amount": "500"}, format="json")
        self.assertEqual((r.status_code, r.json()["message"]), (502, "INVALID_MOBILENUMBER"))
        self.assertEqual(balance(self.user), Decimal("5000.00"))

    @mock.patch("vtu.nellobytes.requests.get")
    def test_verify_meter_goes_through_adapter(self, get):
        get.return_value = http_json({"customer_name": "JOHN DOE"})
        r = self.client.get(reverse("vtu:verify-meter"), {"company": "IKEDC", "meter_no": "1234567890"})
        self.assertEqual(r.json()["customer_name"], "JOHN DOE")
        get.return_value = http_json({"customer_name": "INVALID_METERNO"})
        r = self.client.get(reverse("vtu:verify-meter"), {"company": "IKEDC", "meter_no": "1"})
        self.assertEqual((r.status_code, r.json()["message"]), (400, "INVALID_METERNO"))

    @mock.patch("vtu.nellobytes.requests.get")
    def test_reseller_endpoint_still_works(self, get):
        get.return_value = http_json({"status": "ORDER_RECEIVED", "orderid": "R-1"})
        r = self.client.post("/api/v1/resellers/airtime/purchase/",
                             {"provider_id": 1, "phone_number": "08030000000", "amount": "500"}, format="json")
        self.assertEqual((r.status_code, r.json()["order_id"]), (202, "R-1"))

    def test_admin_pages_render_and_hide_secrets(self):
        admin = User.objects.create_superuser(username="root", email="r@example.com", password="x")
        self.client.force_login(admin)
        r = self.client.get("/admin/vtu/providerstate/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"SUPER-SECRET-KEY-123", r.content)
        state = ProviderState.objects.get(name="nellobytes")
        r = self.client.get(f"/admin/vtu/providerstate/{state.pk}/change/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"SUPER-SECRET-KEY-123", r.content)
        self.assertIn(b"(set)", r.content)
        self.assertEqual(self.client.get("/admin/vtu/purchaseattempt/").status_code, 200)
        self.assertEqual(self.client.get("/admin/wallet/transaction/").status_code, 200)

    @mock.patch("vtu.nellobytes.requests.get")
    def test_admin_connectivity_action_places_no_order(self, get):
        get.return_value = http_json({"balance": "10"})
        admin = User.objects.create_superuser(username="root", email="r@example.com", password="x")
        self.client.force_login(admin)
        state = ProviderState.objects.get_or_create(name="nellobytes")[0]
        self.client.post("/admin/vtu/providerstate/", {"action": "test_connectivity", "_selected_action": [state.pk]})
        self.assertEqual(get.call_count, 1)
        self.assertIn("APIWalletBalanceV1", get.call_args.args[0])
        self.assertEqual(Transaction.objects.count(), 0)
