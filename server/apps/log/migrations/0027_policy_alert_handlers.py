from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0026_alert_organizations_policy_set_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="policy",
            name="handlers",
            field=models.JSONField(default=list, verbose_name="处理人"),
        ),
        migrations.AddField(
            model_name="alert",
            name="handlers",
            field=models.JSONField(default=list, verbose_name="处理人"),
        ),
    ]
