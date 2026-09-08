from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0063_remove_policy_template_scope_name_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorevent",
            name="action",
            field=models.CharField(
                blank=True,
                choices=[
                    ("triggered", "触发"),
                    ("escalated", "级别升级"),
                    ("recovered", "恢复"),
                    ("closed", "人工关闭"),
                ],
                db_index=True,
                default="",
                max_length=20,
                verbose_name="生命周期动作",
            ),
        ),
        migrations.AddIndex(
            model_name="monitorevent",
            index=models.Index(fields=["alert", "action"], name="idx_mon_event_alert_action"),
        ),
        migrations.AddConstraint(
            model_name="monitorevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("action__in", ["triggered", "recovered", "closed"]), ("alert__isnull", False)),
                fields=("alert", "action"),
                name="uniq_monitor_event_alert_status_action",
            ),
        ),
        migrations.AddConstraint(
            model_name="monitorevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("action", "escalated"), ("alert__isnull", False)),
                fields=("alert", "action", "level"),
                name="uniq_monitor_event_alert_escalated_level",
            ),
        ),
    ]
