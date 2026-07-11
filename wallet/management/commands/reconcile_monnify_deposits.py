from django.core.management.base import BaseCommand

from wallet.models import Wallet
from wallet.monnify import MonnifyError, MonnifyService


class Command(BaseCommand):
    help = (
        "Safety net for missed/delayed Monnify webhook calls: polls Monnify for "
        "recent transactions on each reserved account and credits any successful "
        "deposit our system hasn't recorded yet, using the same idempotent credit "
        "logic as the webhook."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--page-size",
            type=int,
            default=20,
            help="How many recent transactions to fetch per reserved account (default: 20).",
        )

    def handle(self, *args, **options):
        size = options["page_size"]
        wallets = Wallet.objects.exclude(account_reference__isnull=True).exclude(account_reference="")

        checked = 0
        credited = 0
        for wallet in wallets:
            checked += 1
            try:
                transactions = MonnifyService.get_reserved_account_transactions(
                    wallet.account_reference, page=0, size=size
                )
            except MonnifyError as e:
                self.stdout.write(f"[SKIP] account_reference={wallet.account_reference} query failed: {e}")
                continue

            for txn in transactions:
                if txn["status"] not in ("PAID", "SUCCESSFUL", "SUCCESS"):
                    continue
                was_credited = MonnifyService.credit_deposit(
                    wallet, txn["amount_paid"], txn["transaction_reference"]
                )
                if was_credited:
                    credited += 1
                    self.stdout.write(
                        f"[OK] account_reference={wallet.account_reference} "
                        f"ref={txn['transaction_reference']} credited"
                    )

        self.stdout.write(f"OK wallets_checked={checked} deposits_credited={credited}")
