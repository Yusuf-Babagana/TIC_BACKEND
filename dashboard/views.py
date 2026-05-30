import io
import sys

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.management import call_command
from django.db.models import Prefetch, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, TemplateView
from django.views import View

from django.contrib.auth import get_user_model

from fashion.models import CustomStyleRequest, Notification, UserMeasurement
from marketing.models import Flyer as FlyerModel, MarketingGallery as MarketingGalleryModel
from vtu.models import DataPlan, Provider
from wallet.models import Transaction, Wallet

UserModel = get_user_model()


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
        for o in orders:
            o.measurement = measurements_map.get(o.user_id)
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


class DashboardPlanToggleView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        plan = get_object_or_404(DataPlan, pk=pk)
        plan.is_active = not plan.is_active
        plan.save(update_fields=["is_active"])
        return JsonResponse({"is_active": plan.is_active, "message": "Plan updated"})


class DashboardPlanPriceUpdateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        plan = get_object_or_404(DataPlan, pk=pk)
        price = request.POST.get("selling_price")
        if price is None:
            return JsonResponse({"error": "selling_price required"}, status=400)
        try:
            plan.selling_price = price
            plan.save(update_fields=["selling_price"])
            return JsonResponse({
                "selling_price": str(plan.selling_price),
                "margin": str(plan.selling_price - (plan.api_price or 0)),
                "message": "Price updated",
            })
        except (ValueError, TypeError) as e:
            return JsonResponse({"error": str(e)}, status=400)


class DashboardPlanSyncView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request):
        margin = request.POST.get("margin", "10")
        buf = io.StringIO()
        try:
            call_command("sync_plans", f"--margin={margin}", stdout=buf)
            output = buf.getvalue()
            return JsonResponse({"message": "Sync completed", "output": output})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


from datetime import date, datetime

from django.db.models import Q
from django.utils import timezone


class DashboardFinanceView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/finance.html"
    login_url = "/dashboard/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.now().date()
        today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        today_end = timezone.make_aware(datetime.combine(today, datetime.max.time()))

        successful = Transaction.objects.filter(status="SUCCESSFUL")

        context["total_revenue"] = successful.aggregate(t=Sum("amount"))["t"] or 0
        context["today_revenue"] = successful.filter(
            created_at__range=(today_start, today_end)
        ).aggregate(t=Sum("amount"))["t"] or 0
        context["total_deposits"] = successful.filter(trans_type="DEPOSIT").aggregate(
            t=Sum("amount")
        )["t"] or 0
        context["total_purchases"] = (
            successful.exclude(trans_type="DEPOSIT").aggregate(t=Sum("amount"))["t"] or 0
        )
        context["total_transactions"] = Transaction.objects.count()
        context["total_wallets"] = Wallet.objects.count()

        q = self.request.GET.get("q", "").strip()
        txn_status = self.request.GET.get("status", "")
        txn_type = self.request.GET.get("type", "")
        date_from = self.request.GET.get("from", "")
        date_to = self.request.GET.get("to", "")
        user_search = self.request.GET.get("user", "").strip()

        qs = Transaction.objects.select_related("user").order_by("-created_at")

        if q:
            qs = qs.filter(
                Q(reference__icontains=q)
                | Q(user__username__icontains=q)
                | Q(user__email__icontains=q)
            )
        if txn_status:
            qs = qs.filter(status=txn_status.upper())
        if txn_type:
            qs = qs.filter(trans_type=txn_type.upper())
        if date_from:
            try:
                qs = qs.filter(
                    created_at__gte=timezone.make_aware(
                        datetime.strptime(date_from, "%Y-%m-%d")
                    )
                )
            except ValueError:
                pass
        if date_to:
            try:
                qs = qs.filter(
                    created_at__lte=timezone.make_aware(
                        datetime.strptime(date_to, "%Y-%m-%d")
                    )
                )
            except ValueError:
                pass
        if user_search:
            qs = qs.filter(
                Q(user__username__icontains=user_search)
                | Q(user__email__icontains=user_search)
                | Q(user__phone_number__icontains=user_search)
            )

        context["transactions"] = qs[:100]
        context["q"] = q
        context["active_status"] = txn_status
        context["active_type"] = txn_type
        context["date_from"] = date_from
        context["date_to"] = date_to
        context["user_search"] = user_search
        return context


class DashboardWalletAdjustView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request):
        from decimal import Decimal, InvalidOperation

        user_id = request.POST.get("user_id")
        action = request.POST.get("action")
        amount_str = request.POST.get("amount")

        if not all([user_id, action, amount_str]):
            return JsonResponse({"error": "user_id, action, and amount required"}, status=400)

        if action not in ("credit", "debit"):
            return JsonResponse({"error": "action must be 'credit' or 'debit'"}, status=400)

        try:
            amount = Decimal(str(amount_str))
            if amount <= 0:
                return JsonResponse({"error": "amount must be positive"}, status=400)
        except InvalidOperation:
            return JsonResponse({"error": "invalid amount"}, status=400)

        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)

        try:
            from django.db import transaction as db_transaction

            with db_transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(user=user)

                if action == "debit" and wallet.balance < amount:
                    return JsonResponse(
                        {"error": f"Insufficient balance (₦{wallet.balance})"}, status=400
                    )

                if action == "credit":
                    wallet.balance += amount
                    ref_prefix = "ADMIN-CREDIT"
                else:
                    wallet.balance -= amount
                    ref_prefix = "ADMIN-DEBIT"

                wallet.save(update_fields=["balance"])

                txn_ref = f"{ref_prefix}-{user.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
                Transaction.objects.create(
                    user=user,
                    trans_type="DEPOSIT" if action == "credit" else "UTILITY",
                    amount=amount,
                    reference=txn_ref,
                    status="SUCCESSFUL",
                )

            return JsonResponse({
                "message": f"Wallet {action}ed ₦{amount}",
                "new_balance": str(wallet.balance),
                "user": user.username,
            })

        except Wallet.DoesNotExist:
            return JsonResponse({"error": "No wallet for this user"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class DashboardUserListView(LoginRequiredMixin, ListView):
    template_name = "dashboard/users.html"
    login_url = "/dashboard/login/"
    context_object_name = "users"
    paginate_by = 50

    def get_queryset(self):
        q = self.request.GET.get("q", "").strip()
        qs = UserModel.objects.all().order_by("-date_joined")
        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(phone_number__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        return context


class DashboardUserDetailView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/user_detail.html"
    login_url = "/dashboard/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = get_object_or_404(UserModel, pk=kwargs["pk"])
        context["profile"] = user

        wallet = Wallet.objects.filter(user=user).first()
        context["wallet"] = wallet

        context["transactions"] = Transaction.objects.filter(user=user).order_by(
            "-created_at"
        )[:50]

        context["tailoring_orders"] = CustomStyleRequest.objects.filter(
            user=user
        ).order_by("-created_at")[:20]
        return context


class DashboardUserToggleActiveView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        user = get_object_or_404(UserModel, pk=pk)
        if user == request.user:
            return JsonResponse({"error": "Cannot block yourself"}, status=400)
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        return JsonResponse({
            "is_active": user.is_active,
            "message": f"User {'unblocked' if user.is_active else 'blocked'}",
        })


class DashboardFlyerView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/flyers.html"
    login_url = "/dashboard/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["flyers"] = FlyerModel.objects.all().order_by("position")
        return context


class DashboardFlyerUploadView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request):
        title = request.POST.get("title", "").strip()
        position = request.POST.get("position")
        link_url = request.POST.get("link_url", "")
        image = request.FILES.get("image")

        if not title:
            return JsonResponse({"error": "Title is required"}, status=400)
        if not position:
            return JsonResponse({"error": "Position is required"}, status=400)
        if not image:
            return JsonResponse({"error": "Image file is required"}, status=400)

        FlyerModel.objects.update_or_create(
            position=position,
            defaults={"title": title, "link_url": link_url, "image": image, "is_active": True},
        )
        return JsonResponse({"message": "Flyer uploaded"})


class DashboardFlyerUpdateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        flyer = get_object_or_404(FlyerModel, pk=pk)
        title = request.POST.get("title", "").strip()
        link_url = request.POST.get("link_url", "")
        image = request.FILES.get("image")

        if title:
            flyer.title = title
        flyer.link_url = link_url
        if image:
            flyer.image = image
        flyer.save(update_fields=["title", "link_url", "image"] if image else ["title", "link_url"])
        return JsonResponse({"message": "Flyer updated"})


class DashboardFlyerDeleteView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        flyer = get_object_or_404(FlyerModel, pk=pk)
        flyer.delete()
        return JsonResponse({"message": "Flyer deleted"})


class DashboardFlyerToggleView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        flyer = get_object_or_404(FlyerModel, pk=pk)
        flyer.is_active = not flyer.is_active
        flyer.save(update_fields=["is_active"])
        return JsonResponse({"is_active": flyer.is_active, "message": "Flyer updated"})


class DashboardGalleryView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/gallery.html"
    login_url = "/dashboard/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["images"] = MarketingGalleryModel.objects.all()
        return context


class DashboardGalleryUploadView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request):
        image = request.FILES.get("image")
        if not image:
            return JsonResponse({"error": "Image file is required"}, status=400)
        MarketingGalleryModel.objects.create(image=image)
        return JsonResponse({"message": "Image uploaded"})


class DashboardGalleryDeleteView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        img = get_object_or_404(MarketingGalleryModel, pk=pk)
        img.delete()
        return JsonResponse({"message": "Image deleted"})
