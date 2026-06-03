from django.contrib import admin

from .models import Referral, ReferralConfig, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["username", "email", "phone_number", "referral_code", "is_verified", "is_staff"]
    search_fields = ["username", "email", "phone_number", "referral_code"]


@admin.register(ReferralConfig)
class ReferralConfigAdmin(admin.ModelAdmin):
    pass


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ["referrer", "referred", "rewarded", "created_at"]
    list_filter = ["rewarded"]
