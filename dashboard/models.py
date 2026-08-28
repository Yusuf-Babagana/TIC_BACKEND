from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    One row per state-changing admin action (any POST under /dashboard/),
    written by dashboard.middleware.AuditLogMiddleware so every mutating
    view is covered automatically — new views don't need to remember to
    log themselves.
    """
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_logs",
    )
    # Denormalized so the log still reads correctly if the actor's account
    # is later deleted, and so a failed-login attempt (no authenticated
    # user yet) still records who it was trying to be.
    actor_username = models.CharField(max_length=150, blank=True, default="")
    action = models.CharField(max_length=100)  # the URL name, e.g. "dashboard_wallet_adjust"
    summary = models.CharField(max_length=255)
    method = models.CharField(max_length=6, default="POST")
    path = models.CharField(max_length=255)
    status_code = models.PositiveSmallIntegerField()
    success = models.BooleanField(default=True)
    details = models.TextField(blank=True, default="")  # sanitized JSON of the request payload
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        who = self.actor_username or "anonymous"
        return f"{who}: {self.summary} ({'ok' if self.success else 'failed'})"


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
