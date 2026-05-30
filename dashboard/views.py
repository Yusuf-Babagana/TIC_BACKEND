from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import TemplateView
from django.views import View

from fashion.models import CustomStyleRequest
from vtu.models import DataPlan
from wallet.models import Transaction, Wallet


class DashboardLoginView(View):
    template_name = "dashboard/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("admin_dashboard")
        return render(request, self.template_name)

    def post(self, request):
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_staff:
            login(request, user)
            next_url = request.GET.get("next", "admin_dashboard")
            return redirect(next_url)
        return render(
            request,
            self.template_name,
            {"error": "Invalid credentials or not a staff member"},
        )


class DashboardLogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("dashboard_login")


class AdminDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"
    login_url = "/dashboard/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["total_wallets"] = Wallet.objects.count()
        context["total_transactions"] = Transaction.objects.count()
        context["total_revenue"] = (
            Transaction.objects.filter(status="SUCCESSFUL").aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        context["tailoring_requests"] = (
            CustomStyleRequest.objects.select_related("user")
            .order_by("-created_at")[:10]
        )
        context["pending_requests"] = (
            CustomStyleRequest.objects.filter(status="pending").count()
        )

        context["active_plans"] = DataPlan.objects.filter(is_active=True).count()

        return context
