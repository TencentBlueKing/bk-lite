from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0017_policy_alert_handlers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apmevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("triggered", "触发"),
                    ("escalated", "级别升级"),
                    ("claimed", "认领"),
                    ("assigned", "分派"),
                    ("recovered", "恢复"),
                    ("closed", "人工关闭"),
                ],
                db_index=True,
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="apmeventsnapshot",
            name="action",
            field=models.CharField(
                choices=[
                    ("triggered", "触发"),
                    ("escalated", "级别升级"),
                    ("claimed", "认领"),
                    ("assigned", "分派"),
                    ("recovered", "恢复"),
                    ("closed", "人工关闭"),
                ],
                max_length=16,
            ),
        ),
    ]
