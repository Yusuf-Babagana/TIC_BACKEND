from django.core.management.base import BaseCommand, CommandError

from vtu.gateway import registry
from wallet.models import Transaction


class Command(BaseCommand):
    help = (
        "READ-ONLY. Lists the newest PENDING transactions and, for those held by Gongoz, asks "
        "Gongoz for the order's raw status word, so you can fill VTU_GONGOZ_SUCCESS_STATUSES / "
        "VTU_GONGOZ_FAILED_STATUSES. Changes nothing and prints no secrets."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20, help="How many newest PENDING orders (default 20).")
        parser.add_argument("--detail", action="store_true",
                            help="Also print each attempt's stored reply and Gongoz's current order body "
                                 "(already redacted: no keys, phone numbers masked).")
        parser.add_argument("--all-statuses", action="store_true",
                            help="Also include non-PENDING Gongoz orders (useful to learn the word for delivered orders).")

    def handle(self, *args, **opts):
        adapter = registry.get_adapter("gongoz")
        if adapter is None or not adapter.config.is_valid:
            raise CommandError("Gongoz is not configured (VTU_GONGOZ_API_KEY missing?).")

        qs = Transaction.objects.all()
        if opts["all_statuses"]:
            qs = qs.filter(provider="gongoz")
        else:
            qs = qs.filter(status="PENDING")
        qs = qs.order_by("-created_at")[: opts["limit"]]

        words = {}
        for t in qs:
            if t.provider == "gongoz" and t.order_id:
                res = adapter.query_status(t.order_id, t.reference)
                word = res.code
                words[word] = words.get(word, 0) + 1
                detail = res.raw
            else:
                word = "(not queried: no Gongoz order id)"
                detail = None
            self.stdout.write(
                f"{t.created_at:%Y-%m-%d %H:%M} {t.trans_type:<8} ours={t.status:<10} "
                f"provider={t.provider or '-':<10} order={t.order_id or '-':<14} gongoz_status={word!r}"
            )
            if opts["detail"] and t.provider == "gongoz":
                for a in t.attempts.all():
                    self.stdout.write(f"    attempt#{a.sequence} {a.provider} outcome={a.outcome} category={a.error_category or '-'} "
                                      f"code={a.code or '-'} ms={a.elapsed_ms} msg={a.message!r}")
                    self.stdout.write(f"      submit reply: {a.response}")
                self.stdout.write(f"      gongoz order now: {detail}")

        self.stdout.write("")
        self.stdout.write("Distinct Gongoz status words seen: " + (repr(words) if words else "none"))
        self.stdout.write("Configured success words: %r" % (adapter.config.get("SUCCESS_STATUSES") or ""))
        self.stdout.write("Configured failed words:  %r" % (adapter.config.get("FAILED_STATUSES") or ""))
