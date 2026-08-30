import logging

logger = logging.getLogger(__name__)


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_webhook_event(provider, outcome, detail="", payload="", ip_address=None, event_type=""):
    """
    Best-effort — a failure recording the log must never break the webhook
    request it's observing, so it's wrapped and logged, never re-raised.
    """
    try:
        from .models import WebhookLog

        WebhookLog.objects.create(
            provider=provider,
            event_type=event_type,
            outcome=outcome,
            detail=detail[:255],
            payload=payload,
            ip_address=ip_address,
        )
    except Exception:
        logger.exception("Failed to record WebhookLog entry: provider=%s outcome=%s", provider, outcome)
