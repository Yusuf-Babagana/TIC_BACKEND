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


class UnifiedPurchaseSerializer(serializers.Serializer):
    CATEGORY_CHOICES = [
        ("DATA", "Data"),
        ("AIRTIME", "Airtime"),
        ("CABLE", "Cable TV"),
        ("ELECTRICITY", "Electricity"),
    ]

    category = serializers.ChoiceField(choices=CATEGORY_CHOICES)
    target_id = serializers.CharField()
    plan_id = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    provider = serializers.CharField(required=False, allow_blank=True)
    meter_type = serializers.ChoiceField(choices=["PREPAID", "POSTPAID"], required=False, default="PREPAID")

    def validate(self, attrs):
        category = attrs.get("category")
        amount = attrs.get("amount")
        if category in ("AIRTIME", "ELECTRICITY") and amount is None:
            raise serializers.ValidationError(
                {"amount": "amount is required for AIRTIME and ELECTRICITY purchases"}
            )
        if category in ("DATA", "AIRTIME", "CABLE", "ELECTRICITY") and not attrs.get("provider"):
            raise serializers.ValidationError(
                {"provider": "provider (network/company) is required for DATA, AIRTIME, CABLE, and ELECTRICITY purchases"}
            )
        return attrs
