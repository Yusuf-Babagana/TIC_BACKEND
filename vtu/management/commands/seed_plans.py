from decimal import Decimal

from django.core.management.base import BaseCommand

from vtu.constants import CABLE_PLANS, DATA_PLANS
from vtu.models import CablePlan, DataPlan, Provider


class Command(BaseCommand):
    help = "Seed DataPlan and CablePlan tables from static constants"

    def handle(self, *args, **options):
        providers_map = {}
        all_providers = [
            ("MTN", 1), ("AIRTEL", 2), ("GLO", 3), ("9MOBILE", 4),
            ("DSTV", 5), ("GOTV", 6), ("STARTIMES", 7),
        ]
        for name, pid in all_providers:
            obj, _ = Provider.objects.get_or_create(
                name=name, defaults={"provider_id": pid}
            )
            providers_map[name] = obj

        self.stdout.write(f"OK {Provider.objects.count()} providers")

        created = 0
        for entry in DATA_PLANS:
            network = entry["provider"].upper()
            provider = providers_map.get(network)
            obj, was = DataPlan.objects.update_or_create(
                plan_id=entry["id"],
                defaults={
                    "provider": provider,
                    "network": network,
                    "plan_name": entry["name"],
                    "bundle_id": entry["id"],
                    "selling_price": Decimal(str(entry["price"])),
                    "is_active": True,
                },
            )
            if was:
                created += 1
        self.stdout.write(f"OK {DataPlan.objects.count()} data plans ({created} new)")

        created = 0
        for entry in CABLE_PLANS:
            pname = entry["provider"].upper()
            provider = providers_map.get(pname)
            obj, was = CablePlan.objects.update_or_create(
                plan_id=entry["id"],
                defaults={
                    "provider": provider,
                    "provider_name": pname,
                    "plan_name": entry["name"],
                    "selling_price": Decimal(str(entry["price"])),
                    "is_active": True,
                },
            )
            if was:
                created += 1
        self.stdout.write(f"OK {CablePlan.objects.count()} cable plans ({created} new)")
