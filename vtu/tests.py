from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from wallet.models import Transaction, Wallet

from .models import CablePlan, DataPlan, ServicePricing
from .pricing import customer_price


class PricingTests(TestCase):
    def test_no_rule_charges_face_amount(self):
        self.assertEqual(customer_price("AIRTIME", "MTN", 100), Decimal("100.00"))

    def test_discount_markup_and_fallback(self):
        ServicePricing.objects.create(category="AIRTIME", provider="*", percent_adjust=Decimal("-1"))
        ServicePricing.objects.create(category="AIRTIME", provider="MTN", percent_adjust=Decimal("-2"))
        ServicePricing.objects.create(category="ELECTRICITY", provider="*", flat_fee=Decimal("50"))
        self.assertEqual(customer_price("AIRTIME", "mtn", 1000), Decimal("980.00"))
        self.assertEqual(customer_price("AIRTIME", "GLO", 1000), Decimal("990.00"))
        self.assertEqual(customer_price("ELECTRICITY", "IKEDC", 2000), Decimal("2050.00"))

    def test_inactive_rule_ignored(self):
        ServicePricing.objects.create(category="AIRTIME", provider="MTN", percent_adjust=Decimal("-5"), is_active=False)
        self.assertEqual(customer_price("AIRTIME", "MTN", 100), Decimal("100.00"))


class SeedKeepsAdminPricesTests(TestCase):
    def test_reseed_preserves_selling_price_but_refreshes_cost(self):
        call_command("seed_plans", verbosity=0)
        plan = DataPlan.objects.get(network="MTN", plan_id="1000.00")
        self.assertEqual(plan.api_price, plan.selling_price)
        plan.selling_price = Decimal("500.00")
        plan.api_price = Decimal("1.00")
        plan.save()
        call_command("seed_plans", verbosity=0)
        plan.refresh_from_db()
        self.assertEqual(plan.selling_price, Decimal("500.00"))
        self.assertEqual(plan.api_price, Decimal("563.00"))
        call_command("seed_plans", "--reset-prices", verbosity=0)
        plan.refresh_from_db()
        self.assertEqual(plan.selling_price, Decimal("563.00"))


class PurchaseUsesAdminPriceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", email="u1@example.com", password="x")
        Wallet.objects.update_or_create(user=self.user, defaults={"balance": Decimal("5000")})
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        DataPlan.objects.create(
            network="MTN", plan_id="1000.00", plan_name="1GB", selling_price=Decimal("350"), api_price=Decimal("400"),
        )

    @mock.patch("vtu.views.NellobytesService")
    def test_data_charges_admin_price(self, svc):
        svc.buy_data.return_value = {"order_id": "O1"}
        r = self.client.post(reverse("vtu:unified-purchase"), {
            "category": "DATA", "provider": "MTN", "plan_id": "1000.00", "target_id": "08030000000",
        }, format="json")
        self.assertEqual(r.status_code, 202, r.content)
        self.assertEqual(Wallet.objects.get(user=self.user).balance, Decimal("4650.00"))

    @mock.patch("vtu.views.NellobytesService")
    def test_airtime_discount_debits_less_but_sends_face_amount(self, svc):
        svc.buy_airtime.return_value = {"order_id": "O2"}
        ServicePricing.objects.create(category="AIRTIME", provider="MTN", percent_adjust=Decimal("-2"))
        r = self.client.post(reverse("vtu:unified-purchase"), {
            "category": "AIRTIME", "provider": "MTN", "plan_id": "x", "target_id": "08030000000", "amount": "1000",
        }, format="json")
        self.assertEqual(r.status_code, 202, r.content)
        self.assertEqual(svc.buy_airtime.call_args.kwargs["amount"], 1000)
        self.assertEqual(Wallet.objects.get(user=self.user).balance, Decimal("4020.00"))
        self.assertEqual(Transaction.objects.get(order_id="O2").amount, Decimal("980.00"))


class DashboardPricingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="adm", email="a@example.com", password="x")
        self.client.force_login(self.admin)
        self.plan = DataPlan.objects.create(
            network="MTN", plan_id="p1", plan_name="1GB", selling_price=Decimal("400"), api_price=Decimal("400"),
        )
        self.cable = CablePlan.objects.create(
            provider_name="DSTV", plan_id="c1", plan_name="Padi", selling_price=Decimal("4400"), api_price=Decimal("4400"),
        )

    def test_page_renders_both_kinds(self):
        self.assertEqual(self.client.get(reverse("dashboard_plans")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard_plans") + "?type=cable&provider=dstv").status_code, 200)

    def test_single_price_update_and_validation(self):
        url = reverse("dashboard_plan_price", args=[self.plan.pk])
        self.assertEqual(self.client.post(url, {"selling_price": "350"}).status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.selling_price, Decimal("350.00"))
        for bad in ("abc", "-5", "0", "NaN", ""):
            self.assertEqual(self.client.post(url, {"selling_price": bad}).status_code, 400, bad)

    def test_cable_price_update(self):
        url = reverse("dashboard_plan_price", args=[self.cable.pk]) + "?type=cable"
        self.assertEqual(self.client.post(url, {"selling_price": "4000"}).status_code, 200)
        self.cable.refresh_from_db()
        self.assertEqual(self.cable.selling_price, Decimal("4000.00"))

    def test_bulk_price(self):
        r = self.client.post(reverse("dashboard_plans_bulk_price"), {"provider": "MTN", "percent": "-12.5"})
        self.assertEqual(r.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.selling_price, Decimal("350.00"))
        self.assertEqual(self.client.post(reverse("dashboard_plans_bulk_price"), {"percent": "-100"}).status_code, 400)

    def test_pricing_rule_create_update_delete(self):
        url = reverse("dashboard_pricing_rule")
        r = self.client.post(url, {"category": "AIRTIME", "provider": "mtn", "percent_adjust": "-2"})
        self.assertEqual(r.status_code, 200)
        self.client.post(url, {"category": "AIRTIME", "provider": "MTN", "percent_adjust": "-3"})
        rule = ServicePricing.objects.get(category="AIRTIME", provider="MTN")
        self.assertEqual(rule.percent_adjust, Decimal("-3.00"))
        self.assertEqual(self.client.post(url, {"category": "AIRTIME", "percent_adjust": "-90"}).status_code, 400)
        self.client.post(reverse("dashboard_pricing_rule_delete", args=[rule.pk]))
        self.assertFalse(ServicePricing.objects.exists())

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse("dashboard_plans_bulk_price"), {"percent": "5"}).status_code, 302)
