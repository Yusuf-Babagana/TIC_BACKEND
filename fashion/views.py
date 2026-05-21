from rest_framework import viewsets, permissions, generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from .models import Category, Product, UserMeasurement, CustomStyleRequest
from .serializers import CategorySerializer, ProductSerializer, UserMeasurementSerializer, CustomStyleRequestSerializer, CustomStyleRequestUpdateSerializer
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