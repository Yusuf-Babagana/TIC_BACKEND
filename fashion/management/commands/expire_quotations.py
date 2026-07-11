from django.core.management.base import BaseCommand
from django.utils import timezone

from fashion.models import CustomStyleRequest


class Command(BaseCommand):
    help = (
        "Flips CustomStyleRequest rows still 'quoted' past their quote_expires_at "
        "to 'expired' — the customer must request a fresh quote after that."
    )

    def handle(self, *args, **options):
        stale = CustomStyleRequest.objects.filter(
            status="quoted",
            quote_expires_at__isnull=False,
            quote_expires_at__lt=timezone.now(),
        )
        count = stale.update(status="expired")
        self.stdout.write(f"OK expired={count}")
