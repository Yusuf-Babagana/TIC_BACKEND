from django.contrib import admin

from .models import Flyer, MarketingGallery


@admin.register(MarketingGallery)
class MarketingGalleryAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "price", "image", "created_at")
    search_fields = ("title",)


@admin.register(Flyer)
class FlyerAdmin(admin.ModelAdmin):
    list_display = ("position", "title", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title",)
