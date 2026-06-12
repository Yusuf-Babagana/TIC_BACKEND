from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model

from .serializers import RegisterSerializer, MyTokenObtainPairSerializer
from .utils import generate_otp
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
            return Response({"message": "OTP sent successfully"}, status=200)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)


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
