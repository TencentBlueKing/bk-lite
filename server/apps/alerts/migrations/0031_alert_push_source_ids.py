from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("alerts", "0030_notification_templates")]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="push_source_ids",
            field=models.JSONField(blank=True, default=list, editable=False, help_text="监控源，关联事件推送来源去重集合"),
        ),
    ]
