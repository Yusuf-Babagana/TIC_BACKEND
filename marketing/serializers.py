from rest_framework import serializers

from .models import Flyer


class FlyerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flyer
        fields = ["id", "title", "image", "link_url", "position", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class PublicFlyerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flyer
        fields = ["id", "title", "image", "link_url", "position"]
