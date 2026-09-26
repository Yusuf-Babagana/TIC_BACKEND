from django.contrib import admin

from .models import FeatureFlag, Referral, ReferralConfig, User


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


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    # Backup access alongside the dashboard's Business Controls page — same underlying rows.
    list_display = ["key", "is_enabled", "updated_at"]
    list_editable = ["is_enabled"]
