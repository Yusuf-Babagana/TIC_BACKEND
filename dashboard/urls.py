from django.urls import path

from .views import (
    AdminDashboardView,
    DashboardFinanceView,
    DashboardLoginView,
    DashboardLogoutView,
    DashboardPlanListView,
    DashboardPlanPriceUpdateView,
    DashboardPlanSyncView,
    DashboardPlanToggleView,
    DashboardTailoringListView,
    DashboardTailoringUpdateView,
    DashboardTransactionListView,
    DashboardWalletAdjustView,
)

urlpatterns = [
    path("", AdminDashboardView.as_view(), name="admin_dashboard"),
    path("login/", DashboardLoginView.as_view(), name="dashboard_login"),
    path("logout/", DashboardLogoutView.as_view(), name="dashboard_logout"),
    path("plans/", DashboardPlanListView.as_view(), name="dashboard_plans"),
    path("plans/sync/", DashboardPlanSyncView.as_view(), name="dashboard_plans_sync"),
    path("plans/<int:pk>/toggle/", DashboardPlanToggleView.as_view(), name="dashboard_plan_toggle"),
    path("plans/<int:pk>/price/", DashboardPlanPriceUpdateView.as_view(), name="dashboard_plan_price"),
    path(
        "transactions/",
        DashboardTransactionListView.as_view(),
        name="dashboard_transactions",
    ),
    path(
        "tailoring/",
        DashboardTailoringListView.as_view(),
        name="dashboard_tailoring",
    ),
    path(
        "tailoring/<int:pk>/update/",
        DashboardTailoringUpdateView.as_view(),
        name="dashboard_tailoring_update",
    ),
    path("finance/", DashboardFinanceView.as_view(), name="dashboard_finance"),
    path("finance/adjust/", DashboardWalletAdjustView.as_view(), name="dashboard_wallet_adjust"),
]
