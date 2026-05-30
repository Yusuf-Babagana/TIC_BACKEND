from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, TemplateView
from django.views import View

from fashion.models import CustomStyleRequest, Notification, UserMeasurement
from vtu.models import DataPlan, Provider
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


class DashboardPlanListView(LoginRequiredMixin, ListView):
    template_name = "dashboard/plans.html"
    login_url = "/dashboard/login/"
    context_object_name = "plans"

    def get_queryset(self):
        provider = self.request.GET.get("provider")
        qs = DataPlan.objects.select_related("provider").order_by(
            "provider__name", "plan_name"
        )
        if provider:
            qs = qs.filter(provider__slug=provider)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["providers"] = Provider.objects.all()
        context["active_provider"] = self.request.GET.get("provider", "")
        return context


class DashboardTransactionListView(LoginRequiredMixin, ListView):
    template_name = "dashboard/transactions.html"
    login_url = "/dashboard/login/"
    context_object_name = "transactions"
    paginate_by = 50

    def get_queryset(self):
        qs = Transaction.objects.select_related("user").order_by("-created_at")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status.upper())
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_status"] = self.request.GET.get("status", "")
        return context


class DashboardTailoringListView(LoginRequiredMixin, ListView):
    template_name = "dashboard/tailoring.html"
    login_url = "/dashboard/login/"
    context_object_name = "requests"
    paginate_by = 50

    def get_queryset(self):
        qs = CustomStyleRequest.objects.select_related("user").order_by("-created_at")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_status"] = self.request.GET.get("status", "")

        orders = context[self.context_object_name]
        user_ids = [o.user_id for o in orders]
        measurements_map = {
            m.user_id: m
            for m in UserMeasurement.objects.filter(user_id__in=user_ids)
        }
        context["measurements_map"] = measurements_map
        return context


class DashboardTailoringUpdateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        order = get_object_or_404(CustomStyleRequest, pk=pk)
        new_status = request.POST.get("status")
        price_quote = request.POST.get("price_quote")

        STATUS_FLOW = {
            "pending": ["cutting"],
            "cutting": ["sewing"],
            "sewing": ["completed"],
            "paid": ["cutting"],
        }

        allowed = STATUS_FLOW.get(order.status, [])
        if new_status not in allowed:
            return JsonResponse(
                {"error": f"Cannot change from '{order.status}' to '{new_status}'"},
                status=400,
            )

        old_status = order.status
        order.status = new_status

        if new_status == "cutting" and price_quote:
            order.price_quote = price_quote

        order.save(update_fields=["status", "price_quote"] if new_status == "cutting" and price_quote else ["status"])

        Notification.objects.create(
            user=order.user,
            order=order,
            message=f"Your tailoring order #{order.id} has been updated from '{old_status}' to '{new_status}'.",
        )

        return JsonResponse({"status": new_status, "message": "Order updated"})
