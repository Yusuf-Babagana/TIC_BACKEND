from rest_framework import status, generics, permissions
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password

from .serializers import (
    ChangeTransactionPinSerializer,
    RegisterSerializer,
    MyTokenObtainPairSerializer,
    ResetPasswordSerializer,
    SetTransactionPinSerializer,
    UserSerializer,
    VerifyTransactionPinSerializer,
)
from .utils import generate_otp, send_otp_email
from wallet.models import Wallet
from wallet.serializers import WalletSerializer

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        otp = generate_otp()
        user.otp_code = otp
        user.save(update_fields=["otp_code"])
        send_otp_email(user.email, otp)

        referral_code = serializer.validated_data.get("referral_code", "")
        if referral_code:
            try:
                from .models import Referral

                referrer = User.objects.get(referral_code=referral_code)
                Referral.objects.get_or_create(referrer=referrer, referred=user)
            except User.DoesNotExist:
                pass

        refresh = RefreshToken.for_user(user)
        wallet_qs = Wallet.objects.filter(user=user)
        wallet_data = (
            WalletSerializer(wallet_qs.first()).data
            if wallet_qs.exists()
            else WalletSerializer(Wallet(user=user)).data
        )

        return Response(
            {
                "message": "User registered successfully. Please verify OTP.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "phone_number": user.phone_number,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
                "token": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
                "wallet": wallet_data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    authentication_classes = []
    permission_classes = [permissions.AllowAny]


class SendOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        phone = request.data.get("phone_number")
        try:
            if email:
                user = User.objects.get(email=email)
            elif phone:
                user = User.objects.get(phone_number=phone)
            else:
                return Response(
                    {"error": "Email or phone_number required"}, status=400
                )
            otp = generate_otp()
            user.otp_code = otp
            user.save(update_fields=["otp_code"])
            send_otp_email(user.email, otp)
            return Response({"message": "OTP sent successfully"}, status=200)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SetTransactionPinView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if request.user.transaction_pin:
            return Response(
                {"error": "PIN already set. Use transaction-pin/change/ to update it."},
                status=400,
            )
        serializer = SetTransactionPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.transaction_pin = make_password(serializer.validated_data["pin"])
        request.user.save(update_fields=["transaction_pin"])
        return Response({"message": "Transaction PIN set successfully"}, status=200)


class ChangeTransactionPinView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangeTransactionPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        current_pin = serializer.validated_data["current_pin"]
        if not user.transaction_pin or not check_password(current_pin, user.transaction_pin):
            return Response({"error": "Current PIN is incorrect"}, status=400)
        user.transaction_pin = make_password(serializer.validated_data["new_pin"])
        user.save(update_fields=["transaction_pin"])
        return Response({"message": "Transaction PIN updated successfully"}, status=200)


class VerifyTransactionPinView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = VerifyTransactionPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        pin = serializer.validated_data["pin"]
        valid = bool(user.transaction_pin) and check_password(pin, user.transaction_pin)
        return Response({"valid": valid}, status=200 if valid else 400)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"error": "refresh is required"}, status=400)
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response({"error": "Invalid or already-blacklisted token"}, status=400)
        return Response({"message": "Logged out successfully"}, status=200)


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            if data.get("email"):
                user = User.objects.get(email=data["email"])
            else:
                user = User.objects.get(phone_number=data["phone_number"])
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        if not user.otp_code or user.otp_code != data["otp"]:
            return Response({"error": "Invalid OTP"}, status=400)

        user.password = make_password(data["new_password"])
        user.otp_code = None
        user.save(update_fields=["password", "otp_code"])
        return Response({"message": "Password reset successfully"}, status=200)


class MyReferralView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .models import Referral

        user = request.user
        referrals = Referral.objects.filter(referrer=user).select_related("referred")
        data = [
            {
                "id": r.id,
                "referred_username": r.referred.username,
                "referred_email": r.referred.email,
                "rewarded": r.rewarded,
                "created_at": r.created_at,
            }
            for r in referrals
        ]
        return Response({
            "referral_code": user.referral_code,
            "referral_link": f"https://ticbackend.pythonanywhere.com/register?ref={user.referral_code}",
            "total_referrals": len(data),
            "referrals": data,
        })


class MyReferralStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .models import Referral, ReferralConfig
        from django.db.models import Sum

        user = request.user
        total_referrals = Referral.objects.filter(referrer=user).count()
        successful_referrals = Referral.objects.filter(referrer=user, rewarded=True).count()
        bonus = ReferralConfig.get_bonus()
        total_earned = successful_referrals * bonus

        return Response({
            "referral_code": user.referral_code,
            "bonus_per_referral": str(bonus),
            "total_referrals": total_referrals,
            "successful_referrals": successful_referrals,
            "total_earned": str(total_earned),
        })


class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        phone = request.data.get("phone_number")
        otp = request.data.get("otp")
        try:
            if email:
                user = User.objects.get(email=email)
            elif phone:
                user = User.objects.get(phone_number=phone)
            else:
                return Response(
                    {"error": "Email or phone_number required"}, status=400
                )
            if user.otp_code == otp:
                user.is_verified = True
                user.otp_code = None
                user.save(update_fields=["is_verified", "otp_code"])
                return Response({"message": "OTP verified successfully"}, status=200)
            return Response({"error": "Invalid OTP"}, status=400)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)
