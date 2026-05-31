from rest_framework import serializers

from .models import Cart, CartItem, Flyer, MarketingGallery, Order, OrderItem


class MarketingGallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketingGallery
        fields = ["id", "title", "price", "description", "image", "created_at"]


class CartItemSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="gallery_item.title", read_only=True)
    price = serializers.DecimalField(source="gallery_item.price", max_digits=12, decimal_places=2, read_only=True)
    image = serializers.ImageField(source="gallery_item.image", read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "gallery_item", "title", "price", "quantity", "total", "image", "created_at"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "items", "total", "created_at"]


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "gallery_item", "title", "price", "quantity", "total", "image_url"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "reference", "total", "status", "delivery_address", "items", "created_at"]


class AddToCartSerializer(serializers.Serializer):
    gallery_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(default=1, min_value=1)


class CheckoutSerializer(serializers.Serializer):
    delivery_address = serializers.CharField(required=False, allow_blank=True)


class FlyerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flyer
        fields = ["id", "title", "image", "link_url", "position", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class PublicFlyerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flyer
        fields = ["id", "title", "image", "link_url", "position"]
