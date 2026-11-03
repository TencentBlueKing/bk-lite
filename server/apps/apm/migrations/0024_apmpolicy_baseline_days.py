from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0023_apmpolicy_judgment_rules"),
    ]

    operations = [
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
                    ("baseline_days", "近 N 天同窗均值"),
                ],
                default="absolute",
                max_length=32,
            ),
        ),
    ]
