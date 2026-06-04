import logging
import uuid

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from wallet.models import Wallet

logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(post_save, sender=User)
def handle_user_onboarding(sender, instance, created, **kwargs):
    if not created:
        return

    if not instance.referral_code:
        instance.referral_code = uuid.uuid4().hex[:10].upper()
        instance.save(update_fields=["referral_code"])

    Wallet.objects.create(user=instance)
