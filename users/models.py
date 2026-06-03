import secrets
import string

from django.contrib.auth.models import AbstractUser
from django.db import models


def generate_referral_code():
    alphabet = string.ascii_uppercase + string.digits
    return "TIC" + "".join(secrets.choice(alphabet) for _ in range(6))


class User(AbstractUser):
    phone_number = models.CharField(max_length=15, unique=True, blank=True, null=True)
    email = models.EmailField(unique=True)
    is_verified = models.BooleanField(default=False)
    referral_code = models.CharField(max_length=12, unique=True, blank=True, null=True)
    otp_code = models.CharField(max_length=6, blank=True, null=True)

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