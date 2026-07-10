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
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["provider", "selling_price"]
        constraints = [
            models.UniqueConstraint(fields=["network", "plan_id"], name="vtu_dataplan_network_plan_id_uniq"),
        ]

    def __str__(self):
        return f"{self.network} - {self.plan_name}"


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
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["provider_name", "selling_price"]
        constraints = [
            models.UniqueConstraint(fields=["provider_name", "plan_id"], name="vtu_cableplan_provider_plan_id_uniq"),
        ]

    def __str__(self):
        return f"{self.provider_name} - {self.plan_name}"
