from django.urls import path

from vtu.views import DataPlanListView, UnifiedPurchaseView

from .views import (
    MonnifyWebhookView,
    SubmitBVNView,
    TransactionHistoryView,
    WalletBalanceView,
)

app_name = "wallet"

urlpatterns = [
    path("balance/", WalletBalanceView.as_view(), name="wallet-balance"),
    path("webhook/monnify", MonnifyWebhookView.as_view(), name="monnify-webhook-no-slash"),
    path("webhook/monnify/", MonnifyWebhookView.as_view(), name="monnify-webhook"),
    path("history/", TransactionHistoryView.as_view(), name="transaction-history"),
    path("submit-bvn/", SubmitBVNView.as_view(), name="submit-bvn"),
    path("plans/", DataPlanListView.as_view(), name="wallet-plans-list"),
    path("purchase/", UnifiedPurchaseView.as_view(), name="wallet-unified-purchase"),
]
