from rest_framework import serializers
from .models import User
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
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

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        validated_data.pop("referral_code", None)
        validated_data["password"] = make_password(validated_data["password"])
        return super().create(validated_data)


class UserSerializer(serializers.ModelSerializer):
    has_transaction_pin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "phone_number",
            "first_name", "last_name", "is_verified", "referral_code",
            "avatar", "kyc_level", "has_transaction_pin",
        ]
        read_only_fields = ["id", "username", "email", "is_verified", "referral_code", "kyc_level"]

    def get_has_transaction_pin(self, obj):
        return bool(obj.transaction_pin)


class SetTransactionPinSerializer(serializers.Serializer):
    pin = serializers.RegexField(r"^\d{4}$", error_messages={"invalid": "PIN must be exactly 4 digits"})


class ChangeTransactionPinSerializer(serializers.Serializer):
    current_pin = serializers.RegexField(r"^\d{4}$", error_messages={"invalid": "PIN must be exactly 4 digits"})
    new_pin = serializers.RegexField(r"^\d{4}$", error_messages={"invalid": "PIN must be exactly 4 digits"})


class VerifyTransactionPinSerializer(serializers.Serializer):
    pin = serializers.RegexField(r"^\d{4}$", error_messages={"invalid": "PIN must be exactly 4 digits"})


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    phone_number = serializers.CharField(required=False)
    otp = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("phone_number"):
            raise serializers.ValidationError("email or phone_number is required")
        return attrs

    def validate_new_password(self, value):
        validate_password(value)
        return value


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
