import re

from django.db import migrations, models

_TRAILING_PAREN = re.compile(r"\(([^()]+)\)\s*$")


def backfill_plan_type(apps, schema_editor):
    """Existing plan names end in their type, e.g. "1 GB - 30 days (Corporate Gifting)"."""
    DataPlan = apps.get_model("vtu", "DataPlan")
    for plan in DataPlan.objects.filter(plan_type=""):
        match = _TRAILING_PAREN.search(plan.plan_name or "")
        if match:
            plan.plan_type = match.group(1).strip().upper()[:40]
            plan.save(update_fields=["plan_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("vtu", "0010_plan_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="dataplan",
            name="plan_type",
            field=models.CharField(blank=True, db_index=True, default="", max_length=40),
        ),
        migrations.AlterField(
            model_name="dataplan",
            name="network",
            field=models.CharField(
                choices=[("MTN", "MTN"), ("AIRTEL", "Airtel"), ("GLO", "Glo"), ("9MOBILE", "9mobile"),
                         ("T2MOBILE", "t2mobile"), ("SMILE", "Smile")],
                max_length=10,
            ),
        ),
        migrations.RunPython(backfill_plan_type, migrations.RunPython.noop),
    ]
