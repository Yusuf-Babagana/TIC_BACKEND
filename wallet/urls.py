from django.urls import path

from .views import (
    GenerateAccountView,
    MonnifyWebhookView,
    SubmitBVNView,
    TransactionHistoryView,
    WalletBalanceView,
)

app_name = "wallet"

urlpatterns = [
    path("balance/", WalletBalanceView.as_view(), name="wallet-balance"),
    path("webhook/monnify/", MonnifyWebhookView.as_view(), name="monnify-webhook"),
    path("history/", TransactionHistoryView.as_view(), name="transaction-history"),
    path("generate-account/", GenerateAccountView.as_view(), name="generate-account"),
    path("submit-bvn/", SubmitBVNView.as_view(), name="submit-bvn"),
]
