from rest_framework import serializers

from .models import DataPlan


class DataPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataPlan
        fields = ["id", "network", "plan_name", "plan_id", "price", "is_active"]


class VTUPurchaseSerializer(serializers.Serializer):
    SERVICE_CHOICES = [
        ("AIRTIME", "Airtime"),
        ("DATA", "Data"),
        ("ELECTRICITY", "Electricity"),
        ("CABLE", "Cable TV"),
        ("EXAMPIN", "Exam Pin"),
    ]

    service_type = serializers.ChoiceField(choices=SERVICE_CHOICES)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    provider_id = serializers.IntegerField(required=False)
    bundle_id = serializers.IntegerField(required=False)
    disco_id = serializers.IntegerField(required=False)
    meter_number = serializers.CharField(required=False, allow_blank=True)
    meter_type = serializers.CharField(required=False, allow_blank=True)
    plan_id = serializers.IntegerField(required=False)
    card_number = serializers.CharField(required=False, allow_blank=True)
    product_id = serializers.IntegerField(required=False)
    quantity = serializers.IntegerField(required=False, default=1)
