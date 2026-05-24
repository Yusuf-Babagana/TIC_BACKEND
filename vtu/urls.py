from django.urls import path
from .views import DataPlanListView, SyncDataPlansView, VTUPurchaseView, UnifiedPurchaseView

urlpatterns = [
    path('plans/', DataPlanListView.as_view(), name='plan-list'),
    path('plans/sync/', SyncDataPlansView.as_view(), name='plan-sync'),
    path('purchase/', VTUPurchaseView.as_view(), name='purchase'),
    path('unified-purchase/', UnifiedPurchaseView.as_view(), name='unified-purchase'),
]
