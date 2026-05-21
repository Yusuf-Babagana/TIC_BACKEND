from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def mask_key(key):
    if not key:
        return "(empty)"
    if len(key) <= 10:
        return key[:4] + "****"
    return key[:6] + "****" + key[-4:]


class Command(BaseCommand):
    help = "Validate CheapDataHub API key format and connectivity"

    def handle(self, *args, **options):
        raw = settings.CHEAPDATAHUB_API_KEY
        masked = mask_key(raw)
        length = len(raw)

        self.stdout.write(f"Raw length ........... {length} characters")
        self.stdout.write(f"Masked value ......... {masked}")
        self.stdout.write(f"First 8 chars ........ '{raw[:8] if raw else '(n/a)'}'")
        self.stdout.write(f"Last 4 chars ......... '{raw[-4:] if raw else '(n/a)'}'")
        self.stdout.write(f"Whitespace stripped .. {raw == raw.strip()}")
        self.stdout.write(f"Prefix 'prod_pk_' .... {raw.startswith('prod_pk_') if raw else False}")

        if not raw:
            raise CommandError(
                "CHEAPDATAHUB_API_KEY is empty. Set it in .env or environment."
            )

        if raw != raw.strip():
            raise CommandError(
                "CHEAPDATAHUB_API_KEY contains leading/trailing whitespace. "
                "Remove spaces or quotes around the value in .env"
            )

        if not raw.startswith("prod_pk_"):
            self.stdout.write(
                self.style.WARNING(
                    "WARNING: Key does not start with expected prefix 'prod_pk_' "
                    "- it may be incorrect or from a different environment."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Prefix validation passed."))

        self.stdout.write(self.style.SUCCESS("\nKey format looks valid.\n"))
