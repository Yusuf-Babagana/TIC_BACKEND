from django.contrib import admin, messages

from .models import Transaction, TransactionEvent, Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "account_number", "bank_name")
    search_fields = ("user__username", "user__email", "account_number")
    readonly_fields = ("balance",)


class TransactionEventInline(admin.TabularInline):
    model = TransactionEvent
    extra = 0
    can_delete = False
    readonly_fields = ("created_at", "from_status", "to_status", "wallet_delta", "balance_after", "source", "detail")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "user",
        "trans_type",
        "amount",
        "status",
        "provider",
        "created_at",
    )
    list_filter = ("status", "trans_type", "provider")
    search_fields = ("reference", "order_id", "user__username", "user__email")
    date_hierarchy = "created_at"
    readonly_fields = ("provider", "idempotency_key", "refunded_at")
    inlines = [TransactionEventInline]
    actions = ["fail_and_refund"]

    @admin.action(description="Mark PENDING as FAILED and refund wallet (only after confirming with the provider!)")
    def fail_and_refund(self, request, queryset):
        from vtu.gateway import ledger
        from vtu.gateway.types import OrderStatus

        done = 0
        for txn in queryset.filter(status="PENDING"):
            if ledger.settle(txn.pk, OrderStatus.FAILED, "admin", f"manual by {request.user.username}"):
                done += 1
        self.message_user(request, f"{done} transaction(s) refunded.", messages.SUCCESS)
