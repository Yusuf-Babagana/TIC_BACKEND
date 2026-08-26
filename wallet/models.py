from decimal import Decimal

from django.db import models
from django.conf import settings

class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Monnify Reserved Account Details
    bank_name = models.CharField(max_length=100, null=True, blank=True)
    account_number = models.CharField(max_length=20, null=True, blank=True)
    account_reference = models.CharField(max_length=100, null=True, blank=True)
    account_name = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.account_number or 'No Acct'} (₦{self.balance})"

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('DATA', 'Data Purchase'),
        ('AIRTIME', 'Airtime Top-up'),
        ('UTILITY', 'Utility Bill'),
        ('DEPOSIT', 'Wallet Funding'),
        ('EXAMPIN', 'Exam Pin Purchase'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SUCCESSFUL', 'Successful'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    trans_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    net_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reference = models.CharField(max_length=100, unique=True) # From CheapDataHub / Monnify / Nellobytes RequestID
    order_id = models.CharField(max_length=100, null=True, blank=True, db_index=True) # Nellobytes orderid
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.trans_type} - {self.amount} ({self.status})"
