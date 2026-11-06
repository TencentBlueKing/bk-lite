from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0054_notification_channel_tags"),
    ]

    operations = [
        migrations.AddField(
            model_name="operationlog",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=128, null=True, unique=True, verbose_name="Idempotency Key"),
        ),
    ]
