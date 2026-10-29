from django.db import migrations, models


class CreateModelIfMissing(migrations.CreateModel):
    """CreateModel that skips the DDL when the table already exists."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.name)
        existing = schema_editor.connection.introspection.table_names()
        if model._meta.db_table in existing:
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):
    """
    0001_initial already *describes* AdminNotification in Django's migration state
    (it was edited in place after being applied), but the real table was never
    created on databases that had already applied it. This uses
    SeparateDatabaseAndState so only the actual DB table gets created, without
    re-registering the model in migration state (which 0001_initial already did).

    The create is skipped when the table exists, so a fresh database (where
    0001_initial already built the table) migrates cleanly too.
    """

    dependencies = [
        ("dashboard", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                CreateModelIfMissing(
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
