import io
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.management import call_command
from django.db.models import Prefetch, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView, TemplateView
from django.views import View

from django.contrib.auth import get_user_model

from fashion.models import (
    CustomStyleRequest,
    FabricBrand,
    FabricColor,
    FabricGrade,
    Notification,
    UserMeasurement,
)
from marketing.models import Flyer as FlyerModel, MarketingGallery as MarketingGalleryModel, Order as OrderModel
from users.models import Referral, ReferralConfig, SiteSettings
from vtu.models import DataPlan, Provider
from vtu.nellobytes import NellobytesError, NellobytesService
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
        today = timezone.now().date()
        today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        today_end = timezone.make_aware(datetime.combine(today, datetime.max.time()))

        successful = Transaction.objects.filter(status="SUCCESSFUL")

        context["total_wallets"] = Wallet.objects.count()
        context["total_transactions"] = Transaction.objects.count()
        context["total_revenue"] = successful.aggregate(total=Sum("amount"))["total"] or 0
        context["today_revenue"] = successful.filter(
            created_at__range=(today_start, today_end)
        ).aggregate(total=Sum("amount"))["total"] or 0

        context["active_plans"] = DataPlan.objects.filter(is_active=True).count()
        context["total_orders"] = OrderModel.objects.count()
        context["pending_orders"] = OrderModel.objects.filter(status="pending").count()
        context["total_users"] = UserModel.objects.filter(is_active=True).count()

        context["tailoring_requests"] = (
            CustomStyleRequest.objects.select_related("user")
            .order_by("-created_at")[:10]
        )
        context["pending_tailoring"] = (
            CustomStyleRequest.objects.filter(status="pending").count()
        )
        context["cutting_sewing"] = (
            CustomStyleRequest.objects.filter(status__in=["cutting", "sewing"]).count()
        )

        context["recent_orders"] = (
            OrderModel.objects.select_related("user")
            .prefetch_related("items")
            .order_by("-created_at")[:8]
        )

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
        qs = CustomStyleRequest.objects.select_related(
            "user", "fabric_grade__brand", "fabric_color"
        ).order_by("-created_at")
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
        fabric_fee = request.POST.get("fabric_fee")
        tailoring_fee = request.POST.get("tailoring_fee")

        STATUS_FLOW = {
            "pending": ["quoted"],
            "quoted": ["cutting"],
            "paid": ["cutting"],
            "cutting": ["sewing"],
            "sewing": ["completed"],
            "completed": ["delivered"],
        }

        allowed = STATUS_FLOW.get(order.status, [])
        if new_status not in allowed:
            return JsonResponse(
                {"error": f"Cannot change from '{order.status}' to '{new_status}'"},
                status=400,
            )

        old_status = order.status
        order.status = new_status

        if new_status == "quoted":
            if fabric_fee in (None, "") or tailoring_fee in (None, ""):
                return JsonResponse(
                    {"error": "Both fabric_fee and tailoring_fee are required"}, status=400
                )
            try:
                fabric_fee_val = Decimal(fabric_fee)
                tailoring_fee_val = Decimal(tailoring_fee)
            except Exception:
                return JsonResponse({"error": "Invalid fee amount"}, status=400)

            order.fabric_fee = fabric_fee_val
            order.tailoring_fee = tailoring_fee_val
            order.price_quote = fabric_fee_val + tailoring_fee_val

        if new_status == "quoted" and old_status != "quoted":
            order.quote_expires_at = timezone.now() + CustomStyleRequest.QUOTE_VALIDITY

        order.save()

        Notification.objects.create(
            user=order.user,
            order=order,
            message=f"Your tailoring order #{order.id} has been updated from '{old_status}' to '{new_status}'.",
        )

        return JsonResponse({"status": new_status, "message": "Order updated"})


class DashboardFabricCatalogView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/fabrics.html"
    login_url = "/dashboard/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["brands"] = FabricBrand.objects.prefetch_related("grades__colors").all()
        return context


class DashboardFabricBrandCreateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request):
        name = request.POST.get("name", "").strip()
        position = request.POST.get("position", "0").strip()
        if not name:
            return JsonResponse({"error": "Name is required"}, status=400)
        try:
            position = int(position) if position else 0
        except ValueError:
            return JsonResponse({"error": "Invalid position"}, status=400)
        FabricBrand.objects.create(name=name, position=position)
        return JsonResponse({"message": "Fabric brand added"})


class DashboardFabricBrandUpdateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        brand = get_object_or_404(FabricBrand, pk=pk)
        name = request.POST.get("name", "").strip()
        position = request.POST.get("position", "").strip()
        if name:
            brand.name = name
        if position:
            try:
                brand.position = int(position)
            except ValueError:
                return JsonResponse({"error": "Invalid position"}, status=400)
        brand.save()
        return JsonResponse({"message": "Fabric brand updated"})


class DashboardFabricBrandDeleteView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        brand = get_object_or_404(FabricBrand, pk=pk)
        brand.delete()
        return JsonResponse({"message": "Fabric brand deleted"})


class DashboardFabricGradeCreateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request):
        brand_id = request.POST.get("brand_id")
        name = request.POST.get("name", "").strip()
        price = request.POST.get("price", "").strip()
        brand = get_object_or_404(FabricBrand, pk=brand_id)
        if not name:
            return JsonResponse({"error": "Name is required"}, status=400)
        if not price:
            return JsonResponse({"error": "Price is required"}, status=400)
        try:
            price = int(price)
        except ValueError:
            return JsonResponse({"error": "Invalid price"}, status=400)
        FabricGrade.objects.create(brand=brand, name=name, price=price)
        return JsonResponse({"message": "Fabric grade added"})


class DashboardFabricGradeUpdateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        grade = get_object_or_404(FabricGrade, pk=pk)
        name = request.POST.get("name", "").strip()
        price = request.POST.get("price", "").strip()
        if name:
            grade.name = name
        if price:
            try:
                grade.price = int(price)
            except ValueError:
                return JsonResponse({"error": "Invalid price"}, status=400)
        grade.save()
        return JsonResponse({"message": "Fabric grade updated"})


class DashboardFabricGradeDeleteView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        grade = get_object_or_404(FabricGrade, pk=pk)
        grade.delete()
        return JsonResponse({"message": "Fabric grade deleted"})


class DashboardFabricColorCreateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request):
        grade_id = request.POST.get("grade_id")
        name = request.POST.get("name", "").strip()
        swatch_image = request.FILES.get("swatch_image")
        grade = get_object_or_404(FabricGrade, pk=grade_id)
        if not name:
            return JsonResponse({"error": "Name is required"}, status=400)
        FabricColor.objects.create(grade=grade, name=name, swatch_image=swatch_image)
        return JsonResponse({"message": "Fabric color added"})


class DashboardFabricColorUpdateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        color = get_object_or_404(FabricColor, pk=pk)
        name = request.POST.get("name", "").strip()
        swatch_image = request.FILES.get("swatch_image")
        if name:
            color.name = name
        if swatch_image:
            color.swatch_image = swatch_image
        color.save()
        return JsonResponse({"message": "Fabric color updated"})


class DashboardFabricColorDeleteView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        color = get_object_or_404(FabricColor, pk=pk)
        color.delete()
        return JsonResponse({"message": "Fabric color deleted"})


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

        # Balance of the account purchases are funded from (see nellobytes.py).
        # Best-effort: never let a slow/down provider break the page.
        try:
            nb_wallet = NellobytesService.get_wallet_balance()
            # Nellobytes formats balance with thousands separators (e.g. "10,071.90").
            context["provider_balance"] = float(str(nb_wallet["balance"]).replace(",", ""))
            context["provider_account_id"] = nb_wallet.get("id")
            context["provider_account_phone"] = nb_wallet.get("phoneno")
        except (NellobytesError, TypeError, ValueError) as e:
            context["provider_balance"] = None
            context["provider_balance_error"] = str(e)

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
        title = request.POST.get("title", "").strip()
        price = request.POST.get("price", "").strip()
        description = request.POST.get("description", "").strip()
        image = request.FILES.get("image")

        if not title:
            return JsonResponse({"error": "Title is required"}, status=400)
        if not price:
            return JsonResponse({"error": "Price is required"}, status=400)
        if not image:
            return JsonResponse({"error": "Image file is required"}, status=400)

        try:
            price = Decimal(price)
        except Exception:
            return JsonResponse({"error": "Invalid price"}, status=400)

        MarketingGalleryModel.objects.create(title=title, price=price, description=description, image=image)
        return JsonResponse({"message": "Gallery item added"})


class DashboardGalleryUpdateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        item = get_object_or_404(MarketingGalleryModel, pk=pk)
        title = request.POST.get("title", "").strip()
        price = request.POST.get("price", "").strip()
        description = request.POST.get("description", "").strip()
        image = request.FILES.get("image")

        if title:
            item.title = title
        if price:
            try:
                item.price = Decimal(price)
            except Exception:
                return JsonResponse({"error": "Invalid price"}, status=400)
        item.description = description
        if image:
            item.image = image
        item.save(update_fields=["title", "price", "description", "image"] if image else ["title", "price", "description"])
        return JsonResponse({"message": "Gallery item updated"})


class DashboardGalleryDeleteView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        img = get_object_or_404(MarketingGalleryModel, pk=pk)
        img.delete()
        return JsonResponse({"message": "Image deleted"})


class DashboardOrderListView(LoginRequiredMixin, ListView):
    template_name = "dashboard/orders.html"
    login_url = "/dashboard/login/"
    context_object_name = "orders"
    paginate_by = 50

    def get_queryset(self):
        qs = OrderModel.objects.all().prefetch_related("items", "user")
        status_filter = self.request.GET.get("status", "")
        if status_filter in dict(OrderModel.STATUS_CHOICES):
            qs = qs.filter(status=status_filter)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_status"] = self.request.GET.get("status", "")
        context["status_choices"] = OrderModel.STATUS_CHOICES
        return context


class DashboardReferralListView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/referrals.html"
    login_url = "/dashboard/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config, _ = ReferralConfig.objects.get_or_create(pk=1)
        context["bonus_amount"] = config.bonus_amount
        context["referrals"] = Referral.objects.select_related("referrer", "referred").all()[:100]
        context["total_referrals"] = Referral.objects.count()
        context["total_bonus_paid"] = Referral.objects.filter(rewarded=True).count() * config.bonus_amount
        return context


class DashboardReferralUpdateBonusView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request):
        amount = request.POST.get("bonus_amount", "").strip()
        if not amount:
            return JsonResponse({"error": "Amount required"}, status=400)
        try:
            amount = Decimal(amount)
            if amount <= 0:
                return JsonResponse({"error": "Amount must be positive"}, status=400)
            config, _ = ReferralConfig.objects.get_or_create(pk=1)
            config.bonus_amount = amount
            config.save(update_fields=["bonus_amount"])
            return JsonResponse({"message": f"Referral bonus updated to ₦{amount}"})
        except Exception:
            return JsonResponse({"error": "Invalid amount"}, status=400)


class DashboardSettingsView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/settings.html"
    login_url = "/dashboard/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site_settings"] = SiteSettings.get_solo()
        return context


class DashboardSettingsUpdateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request):
        whatsapp_number = request.POST.get("whatsapp_number", "").strip()
        settings_obj = SiteSettings.get_solo()
        settings_obj.whatsapp_number = whatsapp_number
        settings_obj.save(update_fields=["whatsapp_number"])
        return JsonResponse({
            "message": "WhatsApp support number updated",
            "whatsapp_number": whatsapp_number,
        })


from .models import AdminNotification


class NotificationPollView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def get(self, request):
        unread = AdminNotification.objects.filter(is_read=False)[:20]
        data = [
            {
                "id": n.id,
                "type": n.notification_type,
                "message": n.message,
                "link": n.link,
                "created_at": n.created_at.strftime("%Y-%m-%d %H:%M"),
            }
            for n in unread
        ]
        return JsonResponse({"notifications": data, "count": len(data)})


class NotificationMarkReadView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        note = get_object_or_404(AdminNotification, pk=pk)
        note.is_read = True
        note.save(update_fields=["is_read"])
        return JsonResponse({"ok": True})


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request):
        AdminNotification.objects.filter(is_read=False).update(is_read=True)
        return JsonResponse({"ok": True})


class DashboardOrderUpdateView(LoginRequiredMixin, View):
    login_url = "/dashboard/login/"

    def post(self, request, pk):
        order = get_object_or_404(OrderModel, pk=pk)
        new_status = request.POST.get("status", "").strip()
        if new_status in dict(OrderModel.STATUS_CHOICES):
            order.status = new_status
            order.save(update_fields=["status"])
            return JsonResponse({"message": f"Order #{order.id} is now {order.get_status_display()}"})
        return JsonResponse({"error": "Invalid status"}, status=400)
