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
            ("DSTV", 5), ("GOTV", 6), ("STARTIMES", 7), ("T2MOBILE", 9),
        ]
        for name, pid in all_providers:
            obj, _ = Provider.objects.get_or_create(
                name=name, defaults={"provider_id": pid}
            )
            providers_map[name] = obj

        self.stdout.write(f"OK {Provider.objects.count()} providers")

        # Deactivate everything first, then reactivate exactly what's in
        # DATA_PLANS — anything no longer present (e.g. stale CheapDataHub-era
        # rows, unsupported 9mobile) ends up is_active=False without deletion.
        DataPlan.objects.update(is_active=False)

        created = 0
        for entry in DATA_PLANS:
            network = entry["provider"].upper()
            provider = providers_map.get(network)
            obj, was = DataPlan.objects.update_or_create(
                network=network,
                plan_id=str(entry["id"]),
                defaults={
                    "provider": provider,
                    "plan_name": entry["name"],
                    "selling_price": Decimal(str(entry["price"])),
                    "is_active": True,
                },
            )
            if was:
                created += 1
        self.stdout.write(f"OK {DataPlan.objects.count()} data plans ({created} new)")

        # Same deactivate-then-reactivate approach as DataPlan — GOTV/STARTIMES
        # rows with no Nellobytes package code end up is_active=False since
        # they're absent from CABLE_PLANS until real codes are supplied.
        CablePlan.objects.update(is_active=False)

        created = 0
        for entry in CABLE_PLANS:
            pname = entry["provider"].upper()
            provider = providers_map.get(pname)
            obj, was = CablePlan.objects.update_or_create(
                provider_name=pname,
                plan_id=str(entry["id"]),
                defaults={
                    "provider": provider,
                    "plan_name": entry["name"],
                    "selling_price": Decimal(str(entry["price"])),
                    "is_active": True,
                },
            )
            if was:
                created += 1
        self.stdout.write(f"OK {CablePlan.objects.count()} cable plans ({created} new)")
