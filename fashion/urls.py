from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, CustomStyleRequestCreateView, CustomStyleRequestAdminView, CustomTailoringView, MyOrdersListView, NotificationListView, NotificationMarkReadView, PayForTailoringView, ProductViewSet, UserMeasurementView

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
    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:pk>/read/', NotificationMarkReadView.as_view(), name='notification-mark-read'),
    path('', include(router.urls)),
]