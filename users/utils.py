import random

from django.db import transaction as db_transaction
from django.utils import timezone


def generate_otp():
    return str(random.randint(100000, 999999))


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

    VTU_TYPES = ["DATA", "AIRTIME", "UTILITY"]
    vtu_count = (
        Txn.objects.filter(user=user, status="SUCCESSFUL", trans_type__in=VTU_TYPES)
        .count()
    )

    if vtu_count != 1:
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