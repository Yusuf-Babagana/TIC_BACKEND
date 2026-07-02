from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import AdminNotification

UserModel = get_user_model()


@receiver(post_save, sender=UserModel)
def user_registered(sender, instance, created, raw, **kwargs):
    if created and not raw:
        AdminNotification.objects.create(
            notification_type="new_user",
            message=f"New user registered: {instance.username} ({instance.email})",
            link=f"/dashboard/users/{instance.pk}/",
        )


@receiver(post_save, sender=UserModel)
def user_referral_notification(sender, instance, created, raw, **kwargs):
    if created and not raw:
        if instance.referred_by.exists():
            AdminNotification.objects.create(
                notification_type="new_referral",
                message=f"New referral: {instance.username} was referred by {instance.referred_by.first().referrer.username}",
                link="/dashboard/referrals/",
            )


def connect_marketing_signals():
    from marketing.models import Order

    @receiver(post_save, sender=Order, weak=False)
    def order_placed(sender, instance, created, raw, **kwargs):
        if created and not raw:
            total_items = instance.items.count()
            AdminNotification.objects.create(
                notification_type="new_order",
                message=f"New market order #{instance.id} by {instance.user.username} — ₦{instance.total} ({total_items} item(s))",
                link="/dashboard/orders/",
            )


def connect_fashion_signals():
    from fashion.models import CustomStyleRequest

    @receiver(post_save, sender=CustomStyleRequest, weak=False)
    def tailoring_requested(sender, instance, created, raw, **kwargs):
        if created and not raw:
            AdminNotification.objects.create(
                notification_type="new_tailoring",
                message=f"New tailoring request #{instance.id} by {instance.user.username} — {instance.description[:80]}",
                link="/dashboard/tailoring/",
            )


def connect_wallet_signals():
    from wallet.models import Transaction

    @receiver(post_save, sender=Transaction, weak=False)
    def transaction_made(sender, instance, created, raw, **kwargs):
        if created and not raw and instance.status == "SUCCESSFUL":
            if instance.trans_type == "DEPOSIT":
                AdminNotification.objects.create(
                    notification_type="new_deposit",
                    message=f"Wallet deposit: {instance.user.username} funded ₦{instance.amount} — {instance.reference}",
                    link="/dashboard/transactions/",
                )
            else:
                AdminNotification.objects.create(
                    notification_type="new_purchase",
                    message=f"Purchase: {instance.user.username} bought ₦{instance.amount} ({instance.trans_type}) — {instance.reference}",
                    link="/dashboard/transactions/",
                )
