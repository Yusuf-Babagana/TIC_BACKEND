from django.urls import path

from .views import (
    AdminDashboardView,
    DashboardLoginView,
    DashboardLogoutView,
    DashboardPlanListView,
    DashboardTailoringListView,
    DashboardTailoringUpdateView,
    DashboardTransactionListView,
)

urlpatterns = [
    path("", AdminDashboardView.as_view(), name="admin_dashboard"),
    path("login/", DashboardLoginView.as_view(), name="dashboard_login"),
    path("logout/", DashboardLogoutView.as_view(), name="dashboard_logout"),
    path("plans/", DashboardPlanListView.as_view(), name="dashboard_plans"),
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
]
