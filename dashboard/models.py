from django.db import models


class AdminNotification(models.Model):
    NOTIFICATION_TYPES = [
        ("new_user", "New User Registration"),
        ("new_order", "New Market Order"),
        ("new_tailoring", "New Tailoring Request"),
        ("new_deposit", "New Wallet Deposit"),
        ("new_purchase", "New VTU Purchase"),
        ("new_referral", "New Referral"),
        ("admin_refund", "Admin Wallet Refund"),
    ]

    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    message = models.CharField(max_length=255)
    link = models.CharField(max_length=255, blank=True, default="")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{'Read' if self.is_read else 'New'}] {self.message[:60]}"
