from django.contrib import admin

from .models import CablePlan, DataPlan, Provider


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "provider_id")
    search_fields = ("name",)


@admin.register(DataPlan)
class DataPlanAdmin(admin.ModelAdmin):
    list_display = ("plan_name", "network", "selling_price", "api_price", "is_active")
    list_editable = ("selling_price", "is_active")
    list_filter = ("network", "is_active")
    search_fields = ("plan_name", "network")


@admin.register(CablePlan)
class CablePlanAdmin(admin.ModelAdmin):
    list_display = ("plan_name", "provider_name", "selling_price", "is_active")
    list_editable = ("selling_price", "is_active")
    list_filter = ("provider_name", "is_active")
    search_fields = ("plan_name",)
