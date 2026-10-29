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

    # VTU gateway bookkeeping (all optional so legacy rows stay valid).
    provider = models.CharField(max_length=30, blank=True, default="", help_text="Provider that holds the live order")
    idempotency_key = models.CharField(max_length=100, null=True, blank=True)
    # Set exactly once when the wallet debit for this row is returned. Guards every
    # refund path (auto, reconcile, admin button) against crediting twice.
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="wallet_txn_user_idem_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.trans_type} - {self.amount} ({self.status})"


class TransactionEvent(models.Model):
    """Append-only audit trail: every status change and wallet movement of a Transaction."""
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=12, blank=True, default="")
    to_status = models.CharField(max_length=12)
    wallet_delta = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    source = models.CharField(max_length=30, blank=True, default="")    # purchase / webhook / reconcile / status-poll / admin
    detail = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.transaction_id}: {self.from_status or '-'} -> {self.to_status}"
