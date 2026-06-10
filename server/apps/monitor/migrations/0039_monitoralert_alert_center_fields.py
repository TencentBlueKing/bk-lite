from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0038_merge_20260608_0310"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitoralert",
            name="alert_center_notified",
            field=models.BooleanField(default=True, verbose_name="告警中心已同步"),
        ),
        migrations.AddField(
            model_name="monitoralert",
            name="alert_center_retry_count",
            field=models.IntegerField(default=0, verbose_name="告警中心通知重试次数"),
        ),
    ]
