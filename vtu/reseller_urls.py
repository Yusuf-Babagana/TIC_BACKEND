from django.urls import path

from .views import (
    AirtimePurchaseView,
    CablePurchaseView,
    DataPurchaseView,
    ElectricityPurchaseView,
)

urlpatterns = [
    path("airtime/purchase/", AirtimePurchaseView.as_view(), name="reseller-airtime-purchase"),
    path("data/purchase/", DataPurchaseView.as_view(), name="reseller-data-purchase"),
    path("electricity/purchase/", ElectricityPurchaseView.as_view(), name="reseller-electricity-purchase"),
    path("cable/purchase/", CablePurchaseView.as_view(), name="reseller-cable-purchase"),
]
