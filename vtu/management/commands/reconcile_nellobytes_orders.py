from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from vtu.nellobytes import NellobytesError, NellobytesService
from wallet.models import Transaction


class Command(BaseCommand):
    help = (
        "Safety net for missed/delayed Nellobytes callbacks: polls Nellobytes' "
        "query endpoint for DATA transactions still PENDING after a few minutes "
        "and resolves them the same way the webhook does."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-minutes",
            type=int,
            default=3,
            help="Only reconcile PENDING transactions older than this many minutes (default: 3).",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=options["older_than_minutes"])
        pending = Transaction.objects.filter(
            trans_type="DATA",
            status="PENDING",
            order_id__isnull=False,
            created_at__lt=cutoff,
        )

        checked = 0
        resolved = 0
        for txn in pending:
            checked += 1
            try:
                body = NellobytesService.query_order(order_id=txn.order_id)
            except NellobytesError as e:
                self.stdout.write(f"[SKIP] order_id={txn.order_id} query failed: {e}")
                continue

            outcome = NellobytesService.resolve_order_outcome(
                body.get("orderstatus") or body.get("status"),
                body.get("statuscode"),
            )
            if outcome in ("SUCCESSFUL", "FAILED"):
                NellobytesService.apply_order_outcome(txn.pk, outcome)
                resolved += 1
                self.stdout.write(f"[OK] order_id={txn.order_id} -> {outcome}")
            else:
                self.stdout.write(f"[PENDING] order_id={txn.order_id} still unresolved")

        self.stdout.write(f"OK checked={checked} resolved={resolved}")
