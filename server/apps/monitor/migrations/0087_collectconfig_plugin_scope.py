from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0086_policy_instance_baseline_dimensions"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectconfig",
            name="plugin_scope",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="唯一键里的模板范围"),
        ),
        migrations.AlterUniqueTogether(
            name="collectconfig",
            unique_together={("monitor_instance", "collector", "collect_type", "config_type", "plugin_scope")},
        ),
    ]
