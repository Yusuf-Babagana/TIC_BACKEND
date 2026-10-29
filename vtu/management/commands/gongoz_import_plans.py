from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from vtu.gateway import registry
from vtu.models import CablePlan, DataPlan

DATA_NETWORKS = {"MTN_PLAN": "MTN", "GLO_PLAN": "GLO", "AIRTEL_PLAN": "AIRTEL", "9MOBILE_PLAN": "9MOBILE"}
CABLE_NAMES = {"DSTV": "DSTV", "GOTV": "GOTV", "STARTIME": "STARTIMES", "STARTIMES": "STARTIMES"}
CENT = Decimal("0.01")


class Command(BaseCommand):
    help = (
        "Make the app serve Gongoz's data and cable plans: imports them from Gongoz's catalogue "
        "(GET /api/user/) as plans whose id IS Gongoz's id (source='gongoz'). Dry run unless --apply. "
        "New plans are priced at Gongoz cost + --margin %; existing imported plans keep their admin-set "
        "selling price (only name/cost refresh). Plans Gongoz dropped are deactivated. "
        "--deactivate-nellobytes hides the old Nellobytes plans so the app only lists Gongoz's."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write changes (default: preview only)")
        parser.add_argument("--margin", type=float, default=0.0,
                            help="Percent added to Gongoz cost for NEW plans' selling price (default 0 = sell at cost)")
        parser.add_argument("--exclude-types", default="TALKMORE",
                            help="Comma-separated Gongoz plan types to skip (default: TALKMORE)")
        parser.add_argument("--types", default="", help="Only import these Gongoz plan types (comma-separated)")
        parser.add_argument("--deactivate-nellobytes", action="store_true",
                            help="Also set the existing Nellobytes data/cable plans inactive")

    def handle(self, *args, **opts):
        adapter = registry.get_adapter("gongoz")
        if not adapter.config.enabled or not adapter.config.is_valid:
            raise CommandError("Enable and configure Gongoz first (VTU_GONGOZ_ENABLED / VTU_GONGOZ_API_KEY).")
        catalog = adapter.fetch_catalog()
        if not catalog:
            raise CommandError("Could not read the Gongoz catalogue (check the token / connectivity).")

        exclude = {t.strip().upper() for t in opts["exclude_types"].split(",") if t.strip()}
        only = {t.strip().upper() for t in opts["types"].split(",") if t.strip()}
        factor = Decimal(str(1 + opts["margin"] / 100))
        apply = opts["apply"]
        self.out = []

        data_rows = self.collect_data(catalog.get("Dataplans") or {}, exclude, only)
        cable_rows = self.collect_cable(catalog.get("Cableplan") or {})
        if not data_rows and not cable_rows:
            raise CommandError("Catalogue contained no plans; nothing changed.")

        with transaction.atomic():
            d = self.sync(DataPlan, data_rows, factor, apply, "network")
            c = self.sync(CablePlan, cable_rows, factor, apply, "provider_name")
            hidden = 0
            if opts["deactivate_nellobytes"] and apply:
                hidden = (DataPlan.objects.filter(source="nellobytes", is_active=True).update(is_active=False)
                          + CablePlan.objects.filter(source="nellobytes", is_active=True).update(is_active=False))

        for line in self.out:
            self.stdout.write(line)
        verb = "APPLIED" if apply else "PREVIEW (nothing written; add --apply)"
        self.stdout.write(f"{verb}: data new={d[0]} updated={d[1]} collisions={d[2]} deactivated={d[3]} | "
                          f"cable new={c[0]} updated={c[1]} collisions={c[2]} deactivated={c[3]} | "
                          f"nellobytes plans hidden={hidden}")
        if apply and factor == 1:
            self.stdout.write("NOTE: new plans are priced AT COST (margin 0). Set prices in the dashboard "
                              "(Plans page bulk %) or re-run with --margin for new plans.")

    # -- collect ----------------------------------------------------------------
    def collect_data(self, data, exclude, only):
        rows = {}
        for key, net in DATA_NETWORKS.items():
            for p in (data.get(key) or {}).get("ALL", []):
                ptype = str(p.get("plan_type", "")).upper()
                if ptype in exclude or (only and ptype not in only):
                    continue
                try:
                    cost = Decimal(str(p["plan_amount"]))
                    pid = str(p["dataplan_id"])
                except (KeyError, ArithmeticError):
                    continue
                if cost <= 0:
                    continue
                name = f"{p.get('plan', '').strip()} - {p.get('month_validate', '').strip()} ({ptype.title()})"
                rows[(net, pid)] = (name[:100], cost)
        return rows

    def collect_cable(self, cable):
        rows = {}
        for key, plans in cable.items():
            if not isinstance(plans, list):
                continue
            for p in plans:
                if "cableplan_id" not in p:
                    continue
                prov = CABLE_NAMES.get(str(p.get("cable", "")).upper())
                try:
                    cost = Decimal(str(p["plan_amount"]))
                except ArithmeticError:
                    continue
                if prov and cost > 0:
                    rows[(prov, str(p["cableplan_id"]))] = (str(p.get("package", "")).strip().strip('"').strip()[:100], cost)
        return rows

    # -- write ------------------------------------------------------------------
    def sync(self, model, rows, factor, apply, net_field):
        new = upd = coll = 0
        seen = set()
        for (net, pid), (name, cost) in sorted(rows.items()):
            seen.add((net, pid))
            existing = model.objects.filter(**{net_field: net, "plan_id": pid}).first()
            if existing and existing.source != "gongoz":
                coll += 1
                self.out.append(f"  SKIP {model.__name__} {net} {pid}: id already used by a {existing.source} plan")
                continue
            if existing:
                upd += 1
                if apply:
                    existing.plan_name, existing.api_price, existing.is_active = name, cost, True
                    existing.save(update_fields=["plan_name", "api_price", "is_active"])
            else:
                new += 1
                if apply:
                    model.objects.create(**{net_field: net, "plan_id": pid, "plan_name": name, "api_price": cost,
                                            "selling_price": (cost * factor).quantize(CENT, rounding=ROUND_HALF_UP),
                                            "source": "gongoz", "is_active": True})
        gone = 0
        for plan in model.objects.filter(source="gongoz", is_active=True):
            if (getattr(plan, net_field), plan.plan_id) not in seen:
                gone += 1
                if apply:
                    plan.is_active = False
                    plan.save(update_fields=["is_active"])
        return new, upd, coll, gone
