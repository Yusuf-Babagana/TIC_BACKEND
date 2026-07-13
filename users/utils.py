import logging
import random

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction as db_transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def generate_otp():
    return str(random.randint(100000, 999999))


def send_customer_email(user, subject, message):
    """
    Best-effort order/request confirmation email to the customer. Wrapped so
    a provider hiccup can never break the checkout/request-submission flow
    that triggered it — same pattern as the admin notification emails.
    """
    if not user.email:
        return
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send customer confirmation email to user id=%s", user.id)


def check_transaction_pin(user, pin):
    """
    Returns (ok, error_message). PIN enforcement only kicks in once a user has
    opted in by setting one (has_transaction_pin) — users who haven't set a
    PIN yet can still spend without one, same as before this was wired in.
    """
    if not user.transaction_pin:
        return True, None
    if not pin:
        return False, "transaction_pin is required"

    from django.contrib.auth.hashers import check_password

    if not check_password(pin, user.transaction_pin):
        return False, "Incorrect transaction PIN"
    return True, None


def send_otp_email(email, otp):
    send_mail(
        subject="Your TIC verification code",
        message=f"Your OTP code is {otp}. It expires once used or a new one is requested.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


def reward_referrer_on_first_purchase(user):
    from .models import Referral, ReferralConfig

    try:
        referral = Referral.objects.select_related("referrer").get(
            referred=user, rewarded=False
        )
    except Referral.DoesNotExist:
        return

    from wallet.models import Transaction as Txn
    from wallet.models import Wallet

    PURCHASE_TYPES = ["DATA", "AIRTIME", "UTILITY", "EXAMPIN"]
    purchase_count = (
        Txn.objects.filter(user=user, status="SUCCESSFUL", trans_type__in=PURCHASE_TYPES)
        .count()
    )

    if purchase_count != 1:
        return

    bonus = ReferralConfig.get_bonus()
    if bonus <= 0:
        return

    try:
        with db_transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=referral.referrer)
            wallet.balance += bonus
            wallet.save(update_fields=["balance"])

            Txn.objects.create(
                user=referral.referrer,
                trans_type="DEPOSIT",
                amount=bonus,
                reference=f"REFREWARD-{referral.referrer.id}-{user.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                status="SUCCESSFUL",
            )

            referral.rewarded = True
            referral.save(update_fields=["rewarded"])
    except Wallet.DoesNotExist:
        pass