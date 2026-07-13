import uuid

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from wallet.models import Transaction, Wallet

from .models import Cart, CartItem, Flyer, MarketingGallery, Order, OrderItem
from .serializers import (
    AddToCartSerializer,
    CartSerializer,
    CheckoutSerializer,
    FlyerSerializer,
    MarketingGallerySerializer,
    OrderSerializer,
    PublicFlyerSerializer,
)


def get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


class CartDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart = get_or_create_cart(request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)


class AddToCartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        gallery_item = get_object_or_404(
            MarketingGallery, pk=serializer.validated_data["gallery_item_id"]
        )
        quantity = serializer.validated_data["quantity"]

        cart = get_or_create_cart(request.user)
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, gallery_item=gallery_item,
            defaults={"quantity": quantity},
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)


class RemoveFromCartView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        cart = get_or_create_cart(request.user)
        cart_item = get_object_or_404(CartItem, pk=pk, cart=cart)
        cart_item.delete()
        return Response(CartSerializer(cart).data)


class UpdateCartItemView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        cart = get_or_create_cart(request.user)
        cart_item = get_object_or_404(CartItem, pk=pk, cart=cart)
        quantity = request.data.get("quantity")
        if quantity is not None and int(quantity) > 0:
            cart_item.quantity = int(quantity)
            cart_item.save()
        return Response(CartSerializer(cart).data)


class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        from users.utils import check_transaction_pin

        pin_ok, pin_error = check_transaction_pin(request.user, request.data.get("transaction_pin"))
        if not pin_ok:
            return Response({"error": pin_error}, status=status.HTTP_400_BAD_REQUEST)

        ser = CheckoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        delivery_address = ser.validated_data.get("delivery_address", "")

        cart = get_or_create_cart(request.user)
        items = list(cart.items.select_related("gallery_item").all())

        if not items:
            return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

        total = cart.total()

        wallet = Wallet.objects.select_for_update().get(user=request.user)
        if wallet.balance < total:
            return Response({"error": "Insufficient wallet balance"}, status=status.HTTP_400_BAD_REQUEST)

        reference = f"ORD-{uuid.uuid4().hex[:12].upper()}"

        order = Order.objects.create(
            user=request.user,
            reference=reference,
            total=total,
            status="pending",
            delivery_address=delivery_address,
        )

        for item in items:
            OrderItem.objects.create(
                order=order,
                gallery_item=item.gallery_item,
                title=item.gallery_item.title,
                price=item.gallery_item.price,
                quantity=item.quantity,
                image_url=item.gallery_item.image.url if item.gallery_item.image else "",
            )

        wallet.balance -= total
        wallet.save(update_fields=["balance"])

        Transaction.objects.create(
            user=request.user,
            reference=reference,
            trans_type="UTILITY",
            amount=total,
            status="SUCCESSFUL",
        )

        from users.utils import reward_referrer_on_first_purchase, send_customer_email
        reward_referrer_on_first_purchase(request.user)

        item_lines = "\n".join(
            f"- {i.quantity}x {i.title} — ₦{i.price} each" for i in order.items.all()
        )
        send_customer_email(
            request.user,
            subject=f"Order Confirmation - {reference}",
            message=(
                f"Hi {request.user.username},\n\n"
                f"Thanks for your order! Here's your confirmation:\n\n"
                f"Order Reference: {reference}\n"
                f"Items:\n{item_lines}\n"
                f"Total: ₦{total}\n"
                f"Delivery Address: {delivery_address or 'Not provided'}\n\n"
                f"We'll notify you once your order status changes.\n\n"
                f"Thanks,\nTIC Team"
            ),
        )

        cart.items.all().delete()

        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class UserOrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(user=request.user).prefetch_related("items")
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)


class UserOrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk, user=request.user)
        serializer = OrderSerializer(order)
        return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def marketing_gallery_list(request):
    images = MarketingGallery.objects.all()
    serializer = MarketingGallerySerializer(images, many=True)
    return Response(serializer.data)


class UserOrderSyncView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from fashion.models import CustomStyleRequest
        from fashion.serializers import CustomStyleRequestSerializer

        gallery_orders = Order.objects.filter(user=request.user).prefetch_related("items")
        tailoring_orders = CustomStyleRequest.objects.filter(user=request.user)

        result = []

        for o in gallery_orders:
            ser = OrderSerializer(o).data
            ser["type"] = "purchase"
            result.append(ser)

        for o in tailoring_orders:
            ser = CustomStyleRequestSerializer(o).data
            ser["type"] = "sewing"
            result.append(ser)

        result.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return Response(result)


class PublicFlyerListView(generics.ListAPIView):
    queryset = Flyer.objects.filter(is_active=True)
    serializer_class = PublicFlyerSerializer
    permission_classes = [permissions.AllowAny]


class FlyerListCreateView(generics.ListCreateAPIView):
    queryset = Flyer.objects.all()
    serializer_class = FlyerSerializer
    permission_classes = [permissions.IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]


class FlyerRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Flyer.objects.all()
    serializer_class = FlyerSerializer
    permission_classes = [permissions.IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]
