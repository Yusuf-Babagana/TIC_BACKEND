from django.contrib import admin
from .models import Category, FabricBrand, FabricColor, FabricGrade, Notification, Product, UserMeasurement, CustomStyleRequest

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

class FabricGradeInline(admin.TabularInline):
    model = FabricGrade
    extra = 1

@admin.register(FabricBrand)
class FabricBrandAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'position')
    ordering = ('position',)
    inlines = [FabricGradeInline]

class FabricColorInline(admin.TabularInline):
    model = FabricColor
    extra = 1

@admin.register(FabricGrade)
class FabricGradeAdmin(admin.ModelAdmin):
    list_display = ('id', 'brand', 'name', 'price')
    list_filter = ('brand',)
    inlines = [FabricColorInline]

@admin.register(FabricColor)
class FabricColorAdmin(admin.ModelAdmin):
    list_display = ('id', 'grade', 'name', 'swatch_image')
    list_filter = ('grade__brand',)

@admin.register(CustomStyleRequest)
class CustomStyleRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'price_quote', 'fabric_grade', 'quote_expires_at', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'user__email', 'description')
    readonly_fields = ('created_at', 'quote_expires_at')

    def save_model(self, request, obj, form, change):
        if change and 'status' in form.changed_data and obj.status == 'quoted':
            from django.utils import timezone
            obj.quote_expires_at = timezone.now() + CustomStyleRequest.QUOTE_VALIDITY
        super().save_model(request, obj, form, change)

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'message', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('user__username', 'user__email', 'message')
