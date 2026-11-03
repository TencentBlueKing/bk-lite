from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0020_apmpolicy_compare_baseline"),
    ]

    operations = [
        migrations.AddField(
            model_name="apmpolicy",
            name="compare_offset_amount",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="apmpolicy",
            name="compare_mode",
            field=models.CharField(
                choices=[
                    ("absolute", "当前值"),
                    ("previous_window", "相对上一等长窗"),
                    ("offset_hours", "N 小时前同窗"),
                    ("offset_days", "N 天前同窗"),
                    ("offset_1h", "1 小时前同窗"),
                    ("offset_24h", "24 小时前同窗"),
                ],
                default="absolute",
                max_length=32,
            ),
        ),
    ]
