from django.db import migrations
from django.db.models import F


def mark_legacy_refunds(apps, schema_editor):
    """
    Before refunded_at existed, a FAILED transaction that carries a provider
    order_id was FAILED by apply_order_outcome, which credited the wallet back.
    (FAILED rows without an order_id never debited the wallet.) Mark the former
    so the admin refund button can't credit them a second time.
    """
    Transaction = apps.get_model("wallet", "Transaction")
    Transaction.objects.filter(
        status__in=["FAILED", "REFUNDED"], order_id__isnull=False, refunded_at__isnull=True,
    ).update(refunded_at=F("created_at"))


class Migration(migrations.Migration):

    dependencies = [
        ("wallet", "0007_gateway"),
    ]

    operations = [
        migrations.RunPython(mark_legacy_refunds, migrations.RunPython.noop),
    ]
