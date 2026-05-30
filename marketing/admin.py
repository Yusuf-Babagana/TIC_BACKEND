from django.contrib import admin

from .models import Flyer


@admin.register(Flyer)
class FlyerAdmin(admin.ModelAdmin):
    list_display = ("position", "title", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title",)
