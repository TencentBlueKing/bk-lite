from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0074_widen_alert_instance_snapshots"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorpolicy",
            name="forecast_target_unit",
            field=models.CharField(
                blank=True,
                default="",
                max_length=50,
                verbose_name="容量线单位",
            ),
        ),
    ]
