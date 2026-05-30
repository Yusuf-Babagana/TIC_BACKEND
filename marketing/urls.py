from django.urls import path

from .views import (
    FlyerListCreateView,
    FlyerRetrieveUpdateDeleteView,
    PublicFlyerListView,
    marketing_gallery_list,
)

urlpatterns = [
    path("gallery/", marketing_gallery_list, name="marketing-gallery"),
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
