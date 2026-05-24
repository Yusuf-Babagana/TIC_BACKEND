from django.urls import path
from .views import DataPlanListView, UnifiedPurchaseView

urlpatterns = [
    path('plans/', DataPlanListView.as_view(), name='plan-list'),
    path('purchase/', UnifiedPurchaseView.as_view(), name='unified-purchase'),
]
