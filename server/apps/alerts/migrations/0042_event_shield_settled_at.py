from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0041_drop_builtin_business_system"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="shield_settled_at",
            field=models.DateTimeField(blank=True, help_text="监控源屏蔽事件已了结时间；空表示仍待窗口结束后重放", null=True),
        ),
        migrations.AddIndex(
            model_name="event",
            index=models.Index(
                fields=["status", "push_source_id", "action", "shield_settled_at", "id"],
                name="event_shield_replay_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="event",
            index=models.Index(
                fields=["source", "push_source_id", "external_id", "action"],
                name="event_recovery_match_idx",
            ),
        ),
    ]
