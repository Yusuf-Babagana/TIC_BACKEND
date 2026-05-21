from django.urls import path

from .views import (
    GenerateAccountView,
    MonnifyWebhookView,
    SubmitBVNView,
    TransactionHistoryView,
)

urlpatterns = [
    path("webhook/", MonnifyWebhookView.as_view(), name="monnify-webhook"),
    path(
        "transactions/",
        TransactionHistoryView.as_view(),
        name="transaction-history",
    ),
    path(
        "generate-account/",
        GenerateAccountView.as_view(),
        name="generate-account",
    ),
    path("submit-bvn/", SubmitBVNView.as_view(), name="submit-bvn"),
]
