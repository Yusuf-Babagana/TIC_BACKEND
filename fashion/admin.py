from django.contrib import admin
from .models import Category, Product, UserMeasurement, CustomStyleRequest

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category', 'price', 'stock', 'is_available', 'created_at')
    list_filter = ('category', 'is_available', 'created_at')
    search_fields = ('name', 'description')

@admin.register(UserMeasurement)
class UserMeasurementAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'neck', 'chest', 'waist', 'shoulder', 'length', 'last_updated')
    search_fields = ('user__username', 'user__email')

@admin.register(CustomStyleRequest)
class CustomStyleRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'price_quote', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'user__email', 'description')
    readonly_fields = ('created_at',)
