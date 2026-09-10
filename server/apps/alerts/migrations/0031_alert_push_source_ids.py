from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("alerts", "0029_alert_event_enrichment_meta")]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="push_source_ids",
            field=models.JSONField(blank=True, default=list, editable=False, help_text="监控源，关联事件推送来源去重集合"),
        ),
    ]
