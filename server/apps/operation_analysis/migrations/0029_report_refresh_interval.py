from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0028_canvas_refresh_interval"),
    ]

    operations = [
        migrations.AddField(
            model_name="report",
            name="refresh_interval",
            field=models.PositiveIntegerField(default=0, verbose_name="刷新周期"),
        ),
    ]
