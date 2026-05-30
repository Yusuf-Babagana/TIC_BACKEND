from django.contrib import admin

from .models import Transaction, Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "account_number", "bank_name")
    search_fields = ("user__username", "user__email", "account_number")
    readonly_fields = ("balance",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "user",
        "trans_type",
        "amount",
        "status",
        "created_at",
    )
    list_filter = ("status", "trans_type")
    search_fields = ("reference", "user__username", "user__email")
    date_hierarchy = "created_at"
