from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("console_mgmt", "0004_add_notification_read"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="recipient_usernames",
            field=models.JSONField(default=list, verbose_name="接收用户"),
        ),
        migrations.AddField(
            model_name="notification",
            name="target_url",
            field=models.CharField(blank=True, default="", max_length=512, verbose_name="跳转地址"),
        ),
        migrations.AddField(
            model_name="notification",
            name="event_key",
            field=models.CharField(blank=True, max_length=200, null=True, unique=True, verbose_name="事件唯一键"),
        ),
    ]
