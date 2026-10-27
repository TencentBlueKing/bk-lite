from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0022_apmpolicy_metric_catalog"),
    ]

    operations = [
        migrations.AddField(
            model_name="apmpolicy",
            name="guard_conditions",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="trigger_window",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="apmpolicy",
            name="recovery_threshold",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="apmpolicytargetstate",
            name="hit_history",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
