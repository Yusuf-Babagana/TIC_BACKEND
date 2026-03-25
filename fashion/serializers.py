from rest_framework import serializers
from .models import Category, Product, UserMeasurement, CustomStyleRequest

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


class CustomStyleRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomStyleRequest
        # Added 'user' to fields and read_only_fields for professional tracking
        fields = ['id', 'user', 'description', 'reference_image', 'status', 'price_quote', 'created_at']
        read_only_fields = ['user', 'status', 'price_quote'] # Only admin can change these