from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ProductViewSet, UserMeasurementView, CustomStyleRequestCreateView

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet)

urlpatterns = [
    path('measurements/', UserMeasurementView.as_view(), name='measurements'),
    path('custom-requests/', CustomStyleRequestCreateView.as_view(), name='custom-request-create'),
    path('', include(router.urls)),
]