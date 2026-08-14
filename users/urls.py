from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    ChangeTransactionPinView,
    LoginView,
    LogoutView,
    MeView,
    MyReferralStatsView,
    MyReferralView,
    RegisterView,
    ResetPasswordView,
    SendOTPView,
    SetTransactionPinView,
    SiteSettingsView,
    VerifyOTPView,
    VerifyTransactionPinView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', MeView.as_view(), name='me'),
    path('send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('transaction-pin/set/', SetTransactionPinView.as_view(), name='set-transaction-pin'),
    path('transaction-pin/change/', ChangeTransactionPinView.as_view(), name='change-transaction-pin'),
    path('transaction-pin/verify/', VerifyTransactionPinView.as_view(), name='verify-transaction-pin'),
    path('referral/', MyReferralView.as_view(), name='my-referral'),
    path('referral/stats/', MyReferralStatsView.as_view(), name='my-referral-stats'),
    path('site-settings/', SiteSettingsView.as_view(), name='site-settings'),
]