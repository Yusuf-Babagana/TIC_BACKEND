from decimal import Decimal

from django.db import transaction
from rest_framework import viewsets, permissions, generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Category, Notification, Product, UserMeasurement, CustomStyleRequest
from .serializers import (
    CategorySerializer,
    CustomStyleRequestSerializer,
    CustomStyleRequestUpdateSerializer,
    NotificationMarkReadSerializer,
    NotificationSerializer,
    ProductSerializer,
    UserMeasurementSerializer,
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all().order_by("id")
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny] # Publicly browsable

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_available=True).order_by("-id")
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Product.objects.filter(is_available=True).order_by("-id")
        category_id = self.request.query_params.get("category")
        if category_id:
            qs = qs.filter(category_id=category_id)
        return qs

class UserMeasurementView(generics.RetrieveUpdateAPIView):
    serializer_class = UserMeasurementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Automatically get or create the measurement profile for the logged-in user
        obj, created = UserMeasurement.objects.get_or_create(user=self.request.user)
        return obj

class CustomStyleRequestCreateView(generics.CreateAPIView):
    queryset = CustomStyleRequest.objects.all()
    serializer_class = CustomStyleRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] # Required for image uploads

    def perform_create(self, serializer):
        # Link the request to the logged-in user
        serializer.save(user=self.request.user)

class MyOrdersListView(generics.ListAPIView):
    serializer_class = CustomStyleRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Only return orders belonging to the logged-in user
        return CustomStyleRequest.objects.filter(user=self.request.user).order_by('-created_at')

class CustomStyleRequestAdminView(generics.RetrieveUpdateAPIView):
    queryset = CustomStyleRequest.objects.all().order_by("-id")
    serializer_class = CustomStyleRequestUpdateSerializer
    permission_classes = [permissions.IsAdminUser]


class CustomTailoringView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        user = request.user
        description = request.data.get("description")
        reference_image = request.FILES.get("reference_image")

        if not description:
            return Response(
                {"error": "description is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        style_request = CustomStyleRequest.objects.create(
            user=user,
            description=description,
            reference_image=reference_image,
        )

        serializer = CustomStyleRequestSerializer(style_request)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PayForTailoringView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from wallet.models import Wallet, Transaction

        user = request.user
        order_id = request.data.get("order_id")

        try:
            order = CustomStyleRequest.objects.get(id=order_id, user=user)
        except CustomStyleRequest.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status != "quoted":
            return Response(
                {"error": f"Order status is '{order.status}', not 'quoted'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if order.price_quote is None or order.price_quote <= 0:
            return Response(
                {"error": "No valid price quote on this order"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(user=user)

                if wallet.balance < order.price_quote:
                    return Response(
                        {"error": "Insufficient balance"},
                        status=status.HTTP_402_PAYMENT_REQUIRED,
                    )

                wallet.balance -= order.price_quote
                wallet.save(update_fields=["balance"])

                order.status = "paid"
                order.save(update_fields=["status"])

                Transaction.objects.create(
                    user=user,
                    trans_type="UTILITY",
                    amount=order.price_quote,
                    status="SUCCESSFUL",
                    reference=f"TAILOR-{order.id}-{order.created_at.strftime('%Y%m%d%H%M%S')}",
                )

            return Response(
                {"message": "Payment successful", "order_id": order.id},
                status=status.HTTP_200_OK,
            )

        except Wallet.DoesNotExist:
            return Response(
                {"error": "Wallet not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationMarkReadView(generics.UpdateAPIView):
    serializer_class = NotificationMarkReadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    def perform_update(self, serializer):
        serializer.save(is_read=True)