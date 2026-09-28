from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0075_monitorpolicy_forecast_target_unit"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorpolicy",
            name="compare_offset_hours",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="对照小时数",
            ),
        ),
    ]
