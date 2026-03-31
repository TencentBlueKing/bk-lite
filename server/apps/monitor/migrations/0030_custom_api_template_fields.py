from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0029_remove_monitorcondition_monitor_object"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorplugin",
            name="display_name",
            field=models.CharField(default="", max_length=100, verbose_name="插件展示名称"),
        ),
        migrations.AddField(
            model_name="monitorplugin",
            name="template_id",
            field=models.CharField(blank=True, max_length=100, null=True, unique=True, verbose_name="模板ID"),
        ),
        migrations.AddField(
            model_name="monitorplugin",
            name="template_type",
            field=models.CharField(default="builtin", max_length=50, verbose_name="模板类型"),
        ),
        migrations.AlterUniqueTogether(
            name="metricgroup",
            unique_together={("monitor_object", "monitor_plugin", "name")},
        ),
        migrations.AlterUniqueTogether(
            name="metric",
            unique_together={("monitor_object", "monitor_plugin", "name")},
        ),
    ]
