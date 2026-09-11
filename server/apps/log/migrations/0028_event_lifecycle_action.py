from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0027_policy_alert_handlers"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="action",
            field=models.CharField(
                blank=True,
                choices=[
                    ("claimed", "认领"),
                    ("assigned", "分派"),
                    ("closed", "人工关闭"),
                ],
                db_index=True,
                default="",
                max_length=20,
                verbose_name="生命周期动作",
            ),
        ),
    ]
