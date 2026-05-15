from django.urls import path
from .views import DataPlanListView, VTUPurchaseView

urlpatterns = [
    path('plans/', DataPlanListView.as_view(), name='plan-list'),
    path('purchase/', VTUPurchaseView.as_view(), name='purchase'),
]
