from django.db import migrations, models


class Migration(migrations.Migration):
    """
    0001_initial already *describes* AdminNotification in Django's migration state
    (it was edited in place after being applied), but the real table was never
    created since Django won't re-run an already-applied migration. This uses
    SeparateDatabaseAndState so only the actual DB table gets created, without
    re-registering the model in migration state (which 0001_initial already did).
    """

    dependencies = [
        ("dashboard", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.CreateModel(
                    name="AdminNotification",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("notification_type", models.CharField(choices=[("new_user", "New User Registration"), ("new_order", "New Market Order"), ("new_tailoring", "New Tailoring Request"), ("new_deposit", "New Wallet Deposit"), ("new_purchase", "New VTU Purchase"), ("new_referral", "New Referral")], max_length=30)),
                        ("message", models.CharField(max_length=255)),
                        ("link", models.CharField(blank=True, default="", max_length=255)),
                        ("is_read", models.BooleanField(default=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                    ],
                    options={
                        "ordering": ["-created_at"],
                    },
                ),
            ],
            state_operations=[],
        ),
    ]
