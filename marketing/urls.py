from django.urls import path

from .views import (
    AddToCartView, CartDetailView, CheckoutView,
    FlyerListCreateView, FlyerRetrieveUpdateDeleteView,
    PublicFlyerListView, RemoveFromCartView, UpdateCartItemView,
    UserOrderDetailView, UserOrderListView, UserOrderSyncView,
    marketing_gallery_list,
)

urlpatterns = [
    path("gallery/", marketing_gallery_list, name="marketing-gallery"),
    path("cart/", CartDetailView.as_view(), name="cart-detail"),
    path("cart/add/", AddToCartView.as_view(), name="cart-add"),
    path("cart/remove/<int:pk>/", RemoveFromCartView.as_view(), name="cart-remove"),
    path("cart/item/<int:pk>/", UpdateCartItemView.as_view(), name="cart-item-update"),
    path("cart/checkout/", CheckoutView.as_view(), name="cart-checkout"),
    path("orders/sync/", UserOrderSyncView.as_view(), name="user-orders-sync"),
    path("orders/", UserOrderListView.as_view(), name="user-orders"),
    path("orders/<int:pk>/", UserOrderDetailView.as_view(), name="user-order-detail"),
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
