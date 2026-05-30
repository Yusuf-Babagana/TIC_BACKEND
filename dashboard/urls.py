from django.urls import path

from .views import AdminDashboardView, DashboardLoginView, DashboardLogoutView

urlpatterns = [
    path("", AdminDashboardView.as_view(), name="admin_dashboard"),
    path("login/", DashboardLoginView.as_view(), name="dashboard_login"),
    path("logout/", DashboardLogoutView.as_view(), name="dashboard_logout"),
]
