from rest_framework import viewsets, permissions, generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Category, Product, UserMeasurement, CustomStyleRequest
from .serializers import CategorySerializer, ProductSerializer, UserMeasurementSerializer, CustomStyleRequestSerializer
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny] # Publicly browsable

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_available=True)
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    
    # Filter by category if requested (FR-15)
    def get_queryset(self):
        queryset = self.queryset
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        return queryset

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