from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0067_policy_alert_handlers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="monitorevent",
            name="action",
            field=models.CharField(
                blank=True,
                choices=[
                    ("triggered", "触发"),
                    ("escalated", "级别升级"),
                    ("claimed", "认领"),
                    ("assigned", "分派"),
                    ("recovered", "恢复"),
                    ("closed", "人工关闭"),
                ],
                db_index=True,
                default="",
                max_length=20,
                verbose_name="生命周期动作",
            ),
        ),
    ]
