from decimal import Decimal

from django.core.management.base import BaseCommand

from vtu.constants import CABLE_PLANS, DATA_PLANS
from vtu.models import CablePlan, DataPlan, Provider


class Command(BaseCommand):
    help = "Sync plan selling prices and api_prices from constants"

    def add_arguments(self, parser):
        parser.add_argument(
            "--margin",
            type=float,
            default=0.0,
            help="Profit margin to add to api_price when setting selling_price (e.g. 10 for 10%%). Uses the 'Price' from constants as api_price when set.",
        )

    def handle(self, *args, **options):
        margin = options["margin"]

        updated = 0
        for entry in DATA_PLANS:
            plan = DataPlan.objects.filter(
                network=entry["provider"].upper(), plan_id=str(entry["id"])
            ).first()
            if not plan:
                continue

            api_price = Decimal(str(entry.get("api_price", entry["price"])))
            if margin:
                selling_price = api_price * Decimal(str(1 + margin / 100))
            else:
                selling_price = Decimal(str(entry["price"]))

            plan.selling_price = selling_price
            plan.api_price = api_price
            plan.save(update_fields=["selling_price", "api_price"])
            updated += 1

        self.stdout.write(f"[OK] {updated} data plans synced")

        updated = 0
        for entry in CABLE_PLANS:
            plan = CablePlan.objects.filter(
                provider_name=entry["provider"].upper(), plan_id=str(entry["id"])
            ).first()
            if not plan:
                continue

            plan.selling_price = Decimal(str(entry["price"]))
            plan.save(update_fields=["selling_price"])
            updated += 1

        self.stdout.write(f"[OK] {updated} cable plans synced")
