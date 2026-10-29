import re

from django.core.management.base import BaseCommand, CommandError

from vtu.gateway import registry
from vtu.models import CablePlan, DataPlan, ProviderPlanCode


def norm(text):
    return re.sub(r"[^a-z0-9+]", "", (text or "").lower())


class Command(BaseCommand):
    help = (
        "Read Gongoz's plan catalogue (GET /api/user/) and suggest which of OUR plans map to which "
        "Gongoz plan id. Prints suggestions only; --apply-cable saves cable mappings where name AND "
        "price match exactly and uniquely. Data plans are never auto-mapped (the catalogues differ "
        "in bundle type/validity): map those by hand in admin -> Provider plan codes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply-cable", action="store_true")
        parser.add_argument("--network", help="Only show data suggestions for this network (MTN/GLO/AIRTEL/9MOBILE)")

    def handle(self, *args, **opts):
        adapter = registry.get_adapter("gongoz")
        if not adapter.config.enabled or not adapter.config.is_valid:
            raise CommandError("Enable and configure Gongoz first (VTU_GONGOZ_ENABLED / VTU_GONGOZ_API_KEY).")
        catalog = adapter.fetch_catalog()
        if not isinstance(catalog, dict):
            raise CommandError("Could not read the Gongoz catalogue (check the token / connectivity).")

        self.cable(catalog.get("Cableplan") or {}, opts["apply_cable"])
        self.data(catalog.get("Dataplans") or {}, (opts["network"] or "").upper())

    def cable(self, cable, apply):
        theirs = {}
        for key, plans in cable.items():
            if not isinstance(plans, list):
                continue
            for p in plans:
                if "cableplan_id" in p:
                    theirs.setdefault((p["cable"].upper().replace("STARTIME", "STARTIMES").replace("STARTIMESS", "STARTIMES"),
                                       norm(p["package"]), str(int(float(p["plan_amount"])))), []).append(p["cableplan_id"])
        self.stdout.write("== CABLE ==")
        saved = 0
        for plan in CablePlan.objects.filter(is_active=True):
            ids = theirs.get((plan.provider_name, norm(plan.plan_name), str(int(plan.selling_price))), [])
            ids = sorted(set(ids))
            if len(ids) == 1:
                self.stdout.write(f"  {plan.provider_name} {plan.plan_name} ({plan.selling_price}) -> gongoz {ids[0]}")
                if apply:
                    ProviderPlanCode.objects.update_or_create(
                        provider="gongoz", service="CABLE", network=plan.provider_name, plan_id=plan.plan_id,
                        defaults={"provider_code": ids[0]})
                    saved += 1
            elif len(ids) > 1:
                self.stdout.write(f"  {plan.provider_name} {plan.plan_name}: ambiguous {ids} - map by hand")
        self.stdout.write(f"  cable mappings saved: {saved}" if apply else "  (dry run; add --apply-cable to save)")

    def data(self, data, only):
        self.stdout.write("== DATA (suggestions by network + price; verify size/validity/type before mapping) ==")
        for key, groups in data.items():
            net = key.replace("_PLAN", "")
            if only and net != only or not isinstance(groups, dict):
                continue
            theirs = {}
            for p in groups.get("ALL", []):
                theirs.setdefault(str(int(float(p["plan_amount"]))), []).append(p)
            for plan in DataPlan.objects.filter(network=net, is_active=True)[:400]:
                cands = theirs.get(str(int(plan.api_price or plan.selling_price)), [])
                for c in cands[:3]:
                    self.stdout.write(
                        f"  {net} ours[{plan.plan_id}] {plan.plan_name!r} ~ gongoz[{c['dataplan_id']}] "
                        f"{c['plan_type']} {c['plan']} {c['month_validate']!r} N{c['plan_amount']}")
