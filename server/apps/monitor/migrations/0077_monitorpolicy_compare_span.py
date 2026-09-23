from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0076_monitorpolicy_compare_offset_hours"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorpolicy",
            name="compare_offset_days",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="对照天数",
            ),
        ),
        migrations.AddField(
            model_name="monitorpolicy",
            name="compare_baseline_weeks",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="对照周数",
            ),
        ),
    ]
