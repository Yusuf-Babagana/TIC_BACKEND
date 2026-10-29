from decimal import Decimal

from django.db import models


class Provider(models.Model):
    name = models.CharField(max_length=50)
    provider_id = models.IntegerField(unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DataPlan(models.Model):
    NETWORK_CHOICES = [
        ('MTN', 'MTN'),
        ('AIRTEL', 'Airtel'),
        ('GLO', 'Glo'),
        ('9MOBILE', '9mobile'),
        ('T2MOBILE', 't2mobile'),
    ]

    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, null=True, blank=True, related_name="data_plans"
    )
    network = models.CharField(max_length=10, choices=NETWORK_CHOICES)
    plan_name = models.CharField(max_length=100)
    plan_id = models.CharField(max_length=20)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    api_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Which provider's plan code `plan_id` is. Imported Gongoz plans carry Gongoz's ids, which must
    # never be sent to Nellobytes (a different provider's code could buy the wrong bundle).
    source = models.CharField(max_length=20, default="nellobytes")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["provider", "selling_price"]
        constraints = [
            models.UniqueConstraint(fields=["network", "plan_id"], name="vtu_dataplan_network_plan_id_uniq"),
        ]

    def __str__(self):
        return f"{self.network} - {self.plan_name}"

    @property
    def margin(self):
        return self.selling_price - (self.api_price or 0)



class CablePlan(models.Model):
    PROVIDER_CHOICES = [
        ('DSTV', 'DSTV'),
        ('GOTV', 'GOTV'),
        ('STARTIMES', 'STARTIMES'),
    ]

    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, null=True, blank=True, related_name="cable_plans"
    )
    provider_name = models.CharField(max_length=10, choices=PROVIDER_CHOICES)
    plan_name = models.CharField(max_length=100)
    plan_id = models.CharField(max_length=40)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    # What Nellobytes charges us; selling_price is what the customer pays.
    api_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Which provider's plan code `plan_id` is. Imported Gongoz plans carry Gongoz's ids, which must
    # never be sent to Nellobytes (a different provider's code could buy the wrong bundle).
    source = models.CharField(max_length=20, default="nellobytes")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["provider_name", "selling_price"]
        constraints = [
            models.UniqueConstraint(fields=["provider_name", "plan_id"], name="vtu_cableplan_provider_plan_id_uniq"),
        ]

    def __str__(self):
        return f"{self.provider_name} - {self.plan_name}"

    @property
    def margin(self):
        return self.selling_price - (self.api_price or 0)



class ServicePricing(models.Model):
    """
    Admin-controlled pricing for services that have no fixed plan price —
    airtime and electricity are bought for a variable amount, so instead of
    a per-plan price the admin sets a rule per provider.

    The customer is charged:  amount + amount * percent_adjust / 100 + flat_fee
    Nellobytes is always sent the face `amount`. A negative percent_adjust is a
    discount (e.g. -2 => customer pays N98 for N100 airtime); a positive value
    or a flat_fee is a markup. A provider of "*" is the fallback for any
    provider without its own rule; no rule at all means the face amount.
    """
    CATEGORY_CHOICES = [
        ("AIRTIME", "Airtime"),
        ("ELECTRICITY", "Electricity"),
    ]

    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES)
    provider = models.CharField(
        max_length=20, default="*",
        help_text="Network / disco code (e.g. MTN, IKEDC) or * for all.",
    )
    percent_adjust = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0"),
        help_text="Negative = discount, positive = markup (percent of amount).",
    )
    flat_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "provider"]
        constraints = [
            models.UniqueConstraint(fields=["category", "provider"], name="vtu_servicepricing_cat_provider_uniq"),
        ]

    def __str__(self):
        return f"{self.category} {self.provider}: {self.percent_adjust}% + {self.flat_fee}"



class ProviderState(models.Model):
    """
    Runtime (non-secret) management data for one registered provider: admin
    on/off switch, priority override, and circuit-breaker health. Credentials
    stay in the environment - nothing sensitive is stored here. Rows are
    created on demand for every provider in the registry.
    """
    name = models.CharField(max_length=30, unique=True)
    admin_enabled = models.BooleanField(default=True, help_text="Runtime switch; the provider must also be enabled in .env")
    priority_override = models.IntegerField(null=True, blank=True, help_text="Lower is tried first. Blank = use the .env / default priority")
    consecutive_failures = models.PositiveIntegerField(default=0)
    suspended_until = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PurchaseAttempt(models.Model):
    """One submission of a Transaction to one provider (failover creates several)."""
    SUBMITTING = "SUBMITTING"   # recorded BEFORE the call, so a crash mid-call still leaves a trace

    transaction = models.ForeignKey("wallet.Transaction", on_delete=models.CASCADE, related_name="attempts")
    provider = models.CharField(max_length=30)
    reference = models.CharField(max_length=100, unique=True, help_text="Request id sent to the provider")
    sequence = models.PositiveSmallIntegerField(default=1)
    outcome = models.CharField(max_length=12, default=SUBMITTING)   # SUBMITTING/ACCEPTED/REJECTED/AMBIGUOUS
    error_category = models.CharField(max_length=20, blank=True, default="")
    code = models.CharField(max_length=100, blank=True, default="")
    message = models.CharField(max_length=255, blank=True, default="")
    provider_order_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    response = models.JSONField(default=dict, blank=True)   # redacted
    elapsed_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["transaction_id", "sequence"]

    def __str__(self):
        return f"{self.provider}#{self.sequence} {self.outcome} ({self.reference})"


class ProviderPlanCode(models.Model):
    """
    Maps one of OUR plans (DataPlan/CablePlan.plan_id, which are Nellobytes codes) to the code a
    different provider uses for the equivalent product. A provider that needs this (e.g. Gongoz)
    only serves a data/cable plan that has a row here, so it never buys the wrong bundle.
    Admin-maintained; contains no secrets.
    """
    SERVICE_CHOICES = [("DATA", "Data"), ("CABLE", "Cable")]

    provider = models.CharField(max_length=30)
    service = models.CharField(max_length=10, choices=SERVICE_CHOICES)
    network = models.CharField(max_length=15, help_text="MTN/GLO/AIRTEL/9MOBILE or DSTV/GOTV/STARTIMES")
    plan_id = models.CharField(max_length=40, help_text="Our DataPlan/CablePlan.plan_id")
    provider_code = models.CharField(max_length=40, help_text="The provider's own plan id")

    class Meta:
        ordering = ["provider", "service", "network", "plan_id"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "service", "network", "plan_id"], name="vtu_providerplancode_uniq"),
        ]

    def __str__(self):
        return f"{self.provider}: {self.network} {self.plan_id} -> {self.provider_code}"
