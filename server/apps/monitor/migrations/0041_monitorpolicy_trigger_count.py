from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0040_monitoralert_idx_alert_center_notified"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorpolicy",
            name="trigger_count",
            field=models.SmallIntegerField(default=1, verbose_name="连续多少个汇聚周期满足阈值触发告警"),
        ),
    ]
