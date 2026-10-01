from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0009_featureflag'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='login_notice_title',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='sitesettings',
            name='login_notice_message',
            field=models.TextField(blank=True, default=''),
        ),
    ]
