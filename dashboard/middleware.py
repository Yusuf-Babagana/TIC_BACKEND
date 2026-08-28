import json
import logging

logger = logging.getLogger(__name__)

# Substrings that mark a POST field as sensitive — never persisted, whatever
# view it shows up on (covers the admin login form today, and anything
# added later without needing this list touched).
_SENSITIVE_FIELD_MARKERS = ("password", "pin", "otp", "token", "secret", "apikey", "api_key")

# Noisy or read-only endpoints that happen to be POST but aren't
# "an admin did something" in the audit-trail sense.
_EXCLUDED_VIEW_NAMES = {
    "dashboard_notification_read",
    "dashboard_notification_read_all",
}

# Friendlier labels for the audit list; anything not listed here falls back
# to a prettified version of the URL name, so new views are covered without
# an update here.
ACTION_LABELS = {
    "dashboard_login": "Admin login attempt",
    "dashboard_wallet_adjust": "Credit/debit user wallet",
    "dashboard_transaction_refund": "Refund failed transaction",
    "dashboard_settings_update": "Update site settings",
    "dashboard_referral_bonus": "Update referral bonus",
    "dashboard_user_toggle": "Block/unblock user",
    "dashboard_plan_toggle": "Toggle data plan",
    "dashboard_plan_price": "Update plan price",
    "dashboard_plans_sync": "Sync plans from provider",
    "dashboard_tailoring_update": "Update tailoring order",
    "dashboard_order_update": "Update market order",
}


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _sanitize_payload(post_data, files_data):
    clean = {}
    for key, value in post_data.items():
        if key == "csrfmiddlewaretoken":
            continue
        if any(marker in key.lower() for marker in _SENSITIVE_FIELD_MARKERS):
            clean[key] = "***redacted***"
        else:
            clean[key] = value
    for key in files_data.keys():
        clean[key] = f"<uploaded file: {files_data[key].name}>"
    return clean


def humanize_action(view_name):
    if not view_name:
        return "Unknown action"
    return ACTION_LABELS.get(view_name, view_name.replace("dashboard_", "").replace("_", " ").capitalize())


class AuditLogMiddleware:
    """
    Best-effort audit trail for the custom admin dashboard. Logs every
    state-changing (POST) request under /dashboard/ — success or failure —
    after the view has run, so it never has to be wired into individual
    views by hand. A logging failure here must never break the request it's
    observing.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._maybe_log(request, response)
        except Exception:
            logger.exception("AuditLogMiddleware failed to record an entry")
        return response

    def _maybe_log(self, request, response):
        if request.method != "POST" or not request.path.startswith("/dashboard/"):
            return

        view_name = getattr(request.resolver_match, "view_name", "") if request.resolver_match else ""
        if view_name in _EXCLUDED_VIEW_NAMES:
            return

        # Import locally: this module is imported by settings.py MIDDLEWARE
        # before the app registry is fully populated.
        from .models import AuditLog

        user = getattr(request, "user", None)
        is_authenticated = bool(user and user.is_authenticated)

        actor_username = user.username if is_authenticated else (request.POST.get("username", "") or "")

        if view_name == "dashboard_login":
            # The login view always answers 200 (re-rendering the form with
            # an error) on bad credentials — only a redirect means it let
            # the attempt through.
            success = response.status_code == 302
        else:
            success = response.status_code < 400

        AuditLog.objects.create(
            actor=user if is_authenticated else None,
            actor_username=actor_username,
            action=view_name or request.path,
            summary=humanize_action(view_name),
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            success=success,
            details=json.dumps(_sanitize_payload(request.POST, request.FILES)),
            ip_address=_client_ip(request),
        )
