from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Flyer, MarketingGallery
from .serializers import (
    FlyerSerializer,
    MarketingGallerySerializer,
    PublicFlyerSerializer,
)


@api_view(["GET"])
@permission_classes([AllowAny])
def marketing_gallery_list(request):
    images = MarketingGallery.objects.all()
    serializer = MarketingGallerySerializer(images, many=True)
    return Response(serializer.data)


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
