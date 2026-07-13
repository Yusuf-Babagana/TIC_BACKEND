from rest_framework import serializers
from .models import Category, FabricBrand, FabricColor, FabricGrade, Notification, Product, UserMeasurement, CustomStyleRequest

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'

class CategorySerializer(serializers.ModelSerializer):
    # Optional: include count of products in each category
    product_count = serializers.IntegerField(source='products.count', read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'image', 'product_count']

class UserMeasurementSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMeasurement
        fields = ['neck', 'chest', 'waist', 'shoulder', 'length']
        # We don't include 'user' here as it's handled by the view via request.user


class FabricColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = FabricColor
        fields = ['id', 'name', 'swatch_image']


class FabricGradeSerializer(serializers.ModelSerializer):
    colors = FabricColorSerializer(many=True, read_only=True)

    class Meta:
        model = FabricGrade
        fields = ['id', 'name', 'price', 'colors']


class FabricBrandSerializer(serializers.ModelSerializer):
    grades = FabricGradeSerializer(many=True, read_only=True)

    class Meta:
        model = FabricBrand
        fields = ['id', 'name', 'position', 'grades']


class CustomStyleRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomStyleRequest
        fields = [
            'id', 'user', 'description', 'reference_image', 'status', 'price_quote',
            'fabric_fee', 'tailoring_fee', 'fabric_grade', 'fabric_color',
            'delivery_address', 'quote_expires_at', 'created_at',
        ]
        read_only_fields = [
            'user', 'status', 'price_quote', 'fabric_fee', 'tailoring_fee', 'quote_expires_at',
        ]

    def validate(self, attrs):
        fabric_grade = attrs.get('fabric_grade')
        fabric_color = attrs.get('fabric_color')
        if fabric_color and fabric_grade and fabric_color.grade_id != fabric_grade.id:
            raise serializers.ValidationError(
                {"fabric_color": "This color does not belong to the selected fabric grade."}
            )
        if fabric_color and not fabric_grade:
            raise serializers.ValidationError(
                {"fabric_color": "fabric_grade is required when fabric_color is set."}
            )
        return attrs

class CustomStyleRequestUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomStyleRequest
        fields = ['status', 'fabric_fee', 'tailoring_fee', 'price_quote', 'quote_expires_at']
        read_only_fields = ['price_quote', 'quote_expires_at']

    def update(self, instance, validated_data):
        from decimal import Decimal

        from django.utils import timezone

        new_status = validated_data.get('status', instance.status)
        if new_status == 'quoted' and instance.status != 'quoted':
            instance.quote_expires_at = timezone.now() + CustomStyleRequest.QUOTE_VALIDITY

        instance = super().update(instance, validated_data)

        if instance.fabric_fee is not None or instance.tailoring_fee is not None:
            instance.price_quote = (instance.fabric_fee or Decimal('0')) + (instance.tailoring_fee or Decimal('0'))
            instance.save(update_fields=['price_quote'])

        return instance

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'order', 'message', 'is_read', 'created_at']

class NotificationMarkReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['is_read']