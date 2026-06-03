from rest_framework import serializers
from .models import User
from django.contrib.auth.hashers import make_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from wallet.models import Wallet
from wallet.serializers import WalletSerializer


class RegisterSerializer(serializers.ModelSerializer):
    referral_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["phone_number", "email", "password", "username", "referral_code"]
        extra_kwargs = {
            "password": {"write_only": True},
            "phone_number": {"required": False, "allow_blank": True},
        }

    def create(self, validated_data):
        validated_data.pop("referral_code", None)
        validated_data["password"] = make_password(validated_data["password"])
        return super().create(validated_data)


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        wallet_qs = Wallet.objects.filter(user=self.user)
        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "phone_number": self.user.phone_number,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
        }
        data["wallet"] = (
            WalletSerializer(wallet_qs.first()).data
            if wallet_qs.exists()
            else WalletSerializer(Wallet(user=self.user)).data
        )
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["phone_number"] = user.phone_number
        return token
