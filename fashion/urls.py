from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ProductViewSet, UserMeasurementView, CustomStyleRequestCreateView, MyOrdersListView, CustomStyleRequestAdminView, CustomTailoringView, PayForTailoringView

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet)

urlpatterns = [
    path('measurements/', UserMeasurementView.as_view(), name='measurements'),
    path('custom-requests/', CustomStyleRequestCreateView.as_view(), name='custom-request-create'),
    path('my-orders/', MyOrdersListView.as_view(), name='my-orders'),
    path('custom-tailoring/', CustomTailoringView.as_view(), name='custom-tailoring'),
    path('pay-tailoring/', PayForTailoringView.as_view(), name='pay-tailoring'),
    path('admin/orders/<int:pk>/', CustomStyleRequestAdminView.as_view(), name='admin-order-update'),
    path('', include(router.urls)),
]