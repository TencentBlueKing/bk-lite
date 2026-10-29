from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0033_homepage_preference"),
    ]

    operations = [
        migrations.AddField(
            model_name="architecture",
            name="refresh_interval",
            field=models.PositiveIntegerField(default=0, verbose_name="刷新周期"),
        ),
    ]
