from django.contrib import admin

from .models import Cart, CartItem, Flyer, MarketingGallery, Order, OrderItem


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "total", "created_at")


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "cart", "gallery_item", "quantity", "total")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "reference", "total", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("reference", "user__username", "delivery_address")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "title", "price", "quantity", "total")


@admin.register(MarketingGallery)
class MarketingGalleryAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "price", "image", "created_at")
    search_fields = ("title",)


@admin.register(Flyer)
class FlyerAdmin(admin.ModelAdmin):
    list_display = ("position", "title", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title",)
