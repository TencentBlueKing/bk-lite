from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0028_event_lifecycle_action"),
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
                ],
                db_index=True,
                default="",
                max_length=20,
                verbose_name="生命周期动作",
            ),
        ),
    ]
