from django.urls import path
from .views import (
    CableVerifyView,
    DataPlanListView,
    MeterVerifyView,
    NellobytesCallbackView,
    ProviderCallbackView,
    UnifiedPurchaseView,
)

app_name = "vtu"

urlpatterns = [
    path('plans/', DataPlanListView.as_view(), name='vtu-plans-list'),
    path('purchase/', UnifiedPurchaseView.as_view(), name='unified-purchase'),
    path('webhook/nellobytes/', NellobytesCallbackView.as_view(), name='nellobytes-webhook'),
    path('webhook/<slug:provider>/', ProviderCallbackView.as_view(), name='provider-webhook'),
    path('verify-cable/', CableVerifyView.as_view(), name='verify-cable'),
    path('verify-meter/', MeterVerifyView.as_view(), name='verify-meter'),
]
