import logging
import uuid

import requests
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from wallet.models import Wallet
from wallet.monnify import MonnifyService, MonnifyError

logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(post_save, sender=User)
def handle_user_onboarding(sender, instance, created, **kwargs):
    if not created:
        return

    if not instance.referral_code:
        instance.referral_code = uuid.uuid4().hex[:10].upper()
        instance.save(update_fields=["referral_code"])

    wallet = Wallet.objects.create(user=instance)

    try:
        account = MonnifyService.create_reserved_account(
            instance, bvn=settings.PROXY_TEST_BVN
        )
        wallet.bank_name = account["bank_name"]
        wallet.account_number = account["account_number"]
        wallet.account_reference = account["account_reference"]
        wallet.save(update_fields=["bank_name", "account_number", "account_reference"])
        logger.info(
            "Monnify account created for user %s: %s - %s",
            instance.username,
            account["bank_name"],
            account["account_number"],
        )
    except MonnifyError:
        logger.exception(
            "Monnify rejected account creation for user %s", instance.username
        )
    except requests.RequestException:
        logger.exception(
            "Network error contacting Monnify for user %s", instance.username
        )
    except Exception:
        logger.exception(
            "Unexpected error during Monnify onboarding for user %s",
            instance.username,
        )
