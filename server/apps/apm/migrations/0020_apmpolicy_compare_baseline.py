from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0019_apmevent_reassign_action"),
    ]

    operations = [
        migrations.AddField(
            model_name="apmpolicy",
            name="compare_mode",
            field=models.CharField(
                choices=[
                    ("absolute", "当前值"),
                    ("previous_window", "相对上一等长窗"),
                    ("offset_1h", "1 小时前同窗"),
                    ("offset_24h", "24 小时前同窗"),
                ],
                default="absolute",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="compare_value_kind",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="min_request_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
