import secrets
import string

from django.contrib.auth.models import AbstractUser
from django.db import models


def generate_referral_code():
    alphabet = string.ascii_uppercase + string.digits
    return "TIC" + "".join(secrets.choice(alphabet) for _ in range(6))


class User(AbstractUser):
    KYC_NONE = "none"
    KYC_TIER1 = "tier1"
    KYC_TIER2 = "tier2"
    KYC_LEVEL_CHOICES = [
        (KYC_NONE, "Unverified"),
        (KYC_TIER1, "Tier 1"),
        (KYC_TIER2, "Tier 2"),
    ]

    phone_number = models.CharField(max_length=15, unique=True, blank=True, null=True)
    email = models.EmailField(unique=True)
    is_verified = models.BooleanField(default=False)
    referral_code = models.CharField(max_length=12, unique=True, blank=True, null=True)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    transaction_pin = models.CharField(max_length=128, blank=True, null=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    kyc_level = models.CharField(max_length=20, choices=KYC_LEVEL_CHOICES, default=KYC_NONE)
    # Expo push token for this user's device — used to deliver notifications (e.g. wallet
    # deposits) even when the app isn't open. Overwritten on every login/app start by the
    # mobile client, so it always reflects the most recently active device.
    push_token = models.CharField(max_length=255, blank=True, null=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['phone_number', 'email']

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = generate_referral_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


class ReferralConfig(models.Model):
    bonus_amount = models.DecimalField(max_digits=10, decimal_places=2, default=100.00)

    class Meta:
        verbose_name = "Referral Config"
        verbose_name_plural = "Referral Config"

    def __str__(self):
        return f"Referral Bonus: ₦{self.bonus_amount}"

    @classmethod
    def get_bonus(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config.bonus_amount


class SiteSettings(models.Model):
    """
    Singleton row (pk=1) for site-wide values the admin can change without a
    deploy — e.g. the WhatsApp support number shown across the app.
    """
    whatsapp_number = models.CharField(max_length=20, blank=True, default="")

    # Message shown on the app's post-login welcome screen. Blank = the app
    # falls back to its built-in default text.
    login_notice_title = models.CharField(max_length=100, blank=True, default="")
    login_notice_message = models.TextField(blank=True, default="")

    # Last successful Nellobytes reseller-balance check, so the Finance
    # Center can show a "last known" figure (with its timestamp) instead of
    # a bare "Unavailable" whenever the live check is currently failing —
    # Nellobytes' balance endpoint has shown recurring transient failures.
    cached_provider_balance = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    cached_provider_balance_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return f"Site Settings (WhatsApp: {self.whatsapp_number or 'not set'})"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class FeatureFlag(models.Model):
    """
    Admin on/off switches for the app's business modules (Marketplace, VTU services, etc.) —
    lets staff pause a section (maintenance, provider outage, restock) without a deploy. Read
    by the mobile app's GET /users/feature-flags/ and toggled from the dashboard's Business
    Controls page. UI-level only: the app shows a "temporarily unavailable" message for a
    disabled feature, this does not itself block the underlying API endpoints.
    """
    KEY_MARKETPLACE = "marketplace"
    KEY_FASHION = "fashion"
    KEY_AIRTIME = "airtime"
    KEY_DATA = "data"
    KEY_CABLE_TV = "cable_tv"
    KEY_ELECTRICITY = "electricity"
    KEY_WALLET_FUNDING = "wallet_funding"
    KEY_CHOICES = [
        (KEY_MARKETPLACE, "Marketplace"),
        (KEY_FASHION, "Fashion / Custom Tailoring"),
        (KEY_AIRTIME, "Airtime Purchase"),
        (KEY_DATA, "Data Bundle Purchase"),
        (KEY_CABLE_TV, "Cable TV Purchase"),
        (KEY_ELECTRICITY, "Electricity Bill Payment"),
        (KEY_WALLET_FUNDING, "Wallet Funding"),
    ]

    key = models.CharField(max_length=30, choices=KEY_CHOICES, unique=True)
    is_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.get_key_display()}: {'ON' if self.is_enabled else 'OFF'}"

    @classmethod
    def get_flags_dict(cls):
        # Every defined key defaults to enabled if it has no row yet, so a freshly-added
        # KEY_CHOICES entry doesn't silently disable a feature before an admin ever touches it.
        existing = dict(cls.objects.values_list("key", "is_enabled"))
        return {key: existing.get(key, True) for key, _ in cls.KEY_CHOICES}


class Referral(models.Model):
    referrer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="referrals_made"
    )
    referred = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="referred_by"
    )
    rewarded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.referrer.username} referred {self.referred.username}"