from rest_framework import serializers
from .models import Category, FabricBrand, FabricGrade, Notification, Product, UserMeasurement, CustomStyleRequest

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


class FabricGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FabricGrade
        fields = ['id', 'name', 'price']


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
            'fabric_grade', 'delivery_address', 'quote_expires_at', 'created_at',
        ]
        read_only_fields = ['user', 'status', 'price_quote', 'quote_expires_at']

class CustomStyleRequestUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomStyleRequest
        fields = ['status', 'price_quote', 'quote_expires_at']
        read_only_fields = ['quote_expires_at']

    def update(self, instance, validated_data):
        from django.utils import timezone

        new_status = validated_data.get('status', instance.status)
        if new_status == 'quoted' and instance.status != 'quoted':
            instance.quote_expires_at = timezone.now() + CustomStyleRequest.QUOTE_VALIDITY
        return super().update(instance, validated_data)

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'order', 'message', 'is_read', 'created_at']

class NotificationMarkReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['is_read']