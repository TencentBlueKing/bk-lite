from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0047_enable_nodemgmtsync_auto_sync_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="collecttaskcredentialhit",
            name="recent_result_event_ids",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="collecttaskcredentialhit",
            name="last_result_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="collecttaskcredentialhit",
            name="last_result_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="collecttaskcredentialhit",
            name="last_result_event_index",
            field=models.IntegerField(default=-1),
        ),
    ]
