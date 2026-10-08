from decimal import Decimal

from django.core.management.base import BaseCommand

from vtu.constants import CABLE_PLANS, DATA_PLANS
from vtu.models import CablePlan, DataPlan, Provider


class Command(BaseCommand):
    help = (
        "Refresh api_price (Nellobytes cost) from constants. selling_price is only "
        "touched when --margin or --reset-prices is given, so admin-set prices survive."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-prices", action="store_true",
            help="Set selling_price back to the constants price (ignored when --margin is set).",
        )
        parser.add_argument(
            "--margin",
            type=float,
            default=0.0,
            help="Profit margin to add to api_price when setting selling_price (e.g. 10 for 10%%). Uses the 'Price' from constants as api_price when set.",
        )

    def handle(self, *args, **options):
        margin = options["margin"]
        reset = options["reset_prices"]

        updated = 0
        for entry in DATA_PLANS:
            plan = DataPlan.objects.filter(
                network=entry["provider"].upper(), plan_id=str(entry["id"])
            ).first()
            if not plan:
                continue

            api_price = Decimal(str(entry.get("api_price", entry["price"])))
            plan.api_price = api_price
            fields = ["api_price"]
            if margin:
                plan.selling_price = (api_price * Decimal(str(1 + margin / 100))).quantize(Decimal("0.01"))
                fields.append("selling_price")
            elif reset:
                plan.selling_price = Decimal(str(entry["price"]))
                fields.append("selling_price")
            plan.save(update_fields=fields)
            updated += 1

        self.stdout.write(f"[OK] {updated} data plans synced")

        updated = 0
        for entry in CABLE_PLANS:
            plan = CablePlan.objects.filter(
                provider_name=entry["provider"].upper(), plan_id=str(entry["id"])
            ).first()
            if not plan:
                continue

            plan.api_price = Decimal(str(entry["price"]))
            fields = ["api_price"]
            if margin:
                plan.selling_price = (plan.api_price * Decimal(str(1 + margin / 100))).quantize(Decimal("0.01"))
                fields.append("selling_price")
            elif reset:
                plan.selling_price = plan.api_price
                fields.append("selling_price")
            plan.save(update_fields=fields)
            updated += 1

        self.stdout.write(f"[OK] {updated} cable plans synced")
