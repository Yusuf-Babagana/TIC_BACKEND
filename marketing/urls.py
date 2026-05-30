from django.urls import path

from .views import (
    FlyerListCreateView,
    FlyerRetrieveUpdateDeleteView,
    PublicFlyerListView,
)

urlpatterns = [
    path("flyers/", PublicFlyerListView.as_view(), name="public-flyers"),
    path(
        "admin/flyers/",
        FlyerListCreateView.as_view(),
        name="admin-flyer-list-create",
    ),
    path(
        "admin/flyers/<int:pk>/",
        FlyerRetrieveUpdateDeleteView.as_view(),
        name="admin-flyer-detail",
    ),
]
