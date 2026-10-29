from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0029_event_reassign_action"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="action",
            field=models.CharField(
                blank=True,
                choices=[
                    ("claimed", "认领"),
                    ("assigned", "分派"),
                    ("reassigned", "转派"),
                    ("closed", "人工关闭"),
                    ("recovered", "自动恢复"),
                ],
                db_index=True,
                default="",
                max_length=20,
                verbose_name="生命周期动作",
            ),
        ),
    ]
