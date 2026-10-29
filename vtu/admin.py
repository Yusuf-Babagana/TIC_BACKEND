from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import Avg, Count, Q
from django.utils import timezone

from .gateway import health, registry, router
from .models import CablePlan, DataPlan, Provider, ProviderPlanCode, ProviderState, PurchaseAttempt, ServicePricing


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
    list_display = ("plan_name", "provider_name", "selling_price", "api_price", "is_active")
    list_editable = ("selling_price", "is_active")
    list_filter = ("provider_name", "is_active")
    search_fields = ("plan_name",)


@admin.register(ServicePricing)
class ServicePricingAdmin(admin.ModelAdmin):
    list_display = ("category", "provider", "percent_adjust", "flat_fee", "is_active", "updated_at")
    list_editable = ("percent_adjust", "flat_fee", "is_active")
    list_filter = ("category", "is_active")


# ---------------------------------------------------------------------------
# VTU provider management. Credentials live in .env only; nothing secret is shown.
# ---------------------------------------------------------------------------

@admin.register(ProviderState)
class ProviderStateAdmin(admin.ModelAdmin):
    list_display = (
        "name", "env_status", "admin_enabled", "priority", "services", "circuit",
        "attempts_24h", "failure_rate_24h", "avg_ms_24h", "last_success_at", "last_error",
    )
    list_editable = ("admin_enabled",)
    fields = ("name", "admin_enabled", "priority_override", "env_status", "config_view", "circuit",
              "consecutive_failures", "suspended_until", "last_success_at", "last_failure_at", "last_error")
    readonly_fields = ("name", "env_status", "config_view", "circuit", "consecutive_failures",
                       "suspended_until", "last_success_at", "last_failure_at", "last_error")
    actions = ["test_connectivity", "reset_circuit"]

    def has_add_permission(self, request):
        return False        # rows are created automatically for every registered provider

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        for name in registry.adapter_classes():
            health.get_state(name)
        return super().get_queryset(request)

    def _adapter(self, obj):
        return registry.get_adapter(obj.name)

    @admin.display(description="Priority")
    def priority(self, obj):
        a = self._adapter(obj)
        return router.effective_priority(a, obj) if a else "-"

    @admin.display(description="Services")
    def services(self, obj):
        a = self._adapter(obj)
        return ", ".join(a.services) if a else "(adapter missing)"

    @admin.display(description=".env")
    def env_status(self, obj):
        a = self._adapter(obj)
        if a is None:
            return "adapter missing"
        if not a.config.enabled:
            return "disabled"
        errs = a.config.errors()
        return "MISCONFIGURED: " + "; ".join(errs) if errs else "enabled"

    @admin.display(description="Settings (secrets hidden)")
    def config_view(self, obj):
        a = self._adapter(obj)
        return ", ".join(f"{k}={v}" for k, v in a.config.public_view().items()) if a else "-"

    @admin.display(description="Circuit")
    def circuit(self, obj):
        if health.is_suspended(obj):
            return f"SUSPENDED until {obj.suspended_until:%Y-%m-%d %H:%M}"
        return f"closed ({obj.consecutive_failures} consecutive failures)"

    def _stats(self, obj):
        since = timezone.now() - timedelta(hours=24)
        return PurchaseAttempt.objects.filter(provider=obj.name, created_at__gte=since).aggregate(
            total=Count("id"),
            bad=Count("id", filter=Q(outcome__in=["REJECTED", "AMBIGUOUS"])),
            ms=Avg("elapsed_ms"),
        )

    @admin.display(description="Attempts (24h)")
    def attempts_24h(self, obj):
        return self._stats(obj)["total"]

    @admin.display(description="Failure rate (24h)")
    def failure_rate_24h(self, obj):
        s = self._stats(obj)
        return f"{100 * s['bad'] / s['total']:.0f}%" if s["total"] else "-"

    @admin.display(description="Avg ms (24h)")
    def avg_ms_24h(self, obj):
        ms = self._stats(obj)["ms"]
        return int(ms) if ms else "-"

    @admin.action(description="Test connectivity (read-only, places NO order)")
    def test_connectivity(self, request, queryset):
        for obj in queryset:
            a = self._adapter(obj)
            if a is None or not a.config.enabled or not a.config.is_valid:
                self.message_user(request, f"{obj.name}: not enabled/configured in .env", messages.WARNING)
                continue
            r = a.check_connectivity()
            level = messages.SUCCESS if r["ok"] else messages.ERROR
            self.message_user(request, f"{obj.name}: {'OK' if r['ok'] else 'FAILED'} - {r['detail']} ({r['elapsed_ms']}ms)", level)

    @admin.action(description="Clear failures / lift suspension")
    def reset_circuit(self, request, queryset):
        for obj in queryset:
            health.reset(obj.name)
        self.message_user(request, "Circuit reset.")


@admin.register(ProviderPlanCode)
class ProviderPlanCodeAdmin(admin.ModelAdmin):
    """Which of OUR plans each provider can fulfil, and under what code (see docs/VTU_PROVIDERS.md)."""
    list_display = ("provider", "service", "network", "plan_id", "provider_code")
    list_filter = ("provider", "service", "network")
    search_fields = ("plan_id", "provider_code")


@admin.register(PurchaseAttempt)
class PurchaseAttemptAdmin(admin.ModelAdmin):
    """Failover log: every submission of a transaction to a provider."""
    list_display = ("created_at", "reference", "provider", "sequence", "outcome", "error_category", "code", "elapsed_ms")
    list_filter = ("provider", "outcome", "error_category")
    search_fields = ("reference", "provider_order_id", "transaction__reference")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
