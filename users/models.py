from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    # Using phone number as a primary requirement (FR-1)
    phone_number = models.CharField(max_length=15, unique=True, blank=True, null=True)
    email = models.EmailField(unique=True)
    is_verified = models.BooleanField(default=False)  # For OTP (FR-3)
    referral_code = models.CharField(max_length=12, unique=True, blank=True, null=True) # (FR-21)
    otp_code = models.CharField(max_length=6, blank=True, null=True)

    # Reverting to default username for login
    USERNAME_FIELD = 'username' 
    REQUIRED_FIELDS = ['phone_number', 'email']

    def __str__(self):
        return self.username