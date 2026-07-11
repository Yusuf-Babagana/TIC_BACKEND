import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fashion', '0005_fabricbrand_customstylerequest_quote_expires_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='customstylerequest',
            name='fabric_grade',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requests', to='fashion.fabricgrade'),
        ),
    ]
