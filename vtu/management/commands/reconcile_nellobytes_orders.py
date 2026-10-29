from django.core.management.base import BaseCommand

from vtu.gateway import engine


class Command(BaseCommand):
    help = (
        "Safety net for missed/delayed provider callbacks: asks the provider holding each "
        "PENDING Data/Airtime/Utility order for its real status and settles it exactly as the "
        "webhook does. Only a confirmed provider answer changes anything - unknown/pending "
        "answers and query errors leave the order PENDING (never auto-refunded). Schedule it "
        "every few minutes. (Name kept for existing cron jobs; it now covers every provider.)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-minutes", type=int, default=3,
            help="Only reconcile PENDING transactions older than this many minutes (default: 3).",
        )

    def handle(self, *args, **options):
        checked, resolved = engine.reconcile_pending(options["older_than_minutes"])
        self.stdout.write(f"OK checked={checked} resolved={resolved}")
