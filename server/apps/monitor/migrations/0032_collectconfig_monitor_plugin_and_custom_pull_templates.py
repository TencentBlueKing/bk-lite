from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0031_monitorobject_display_name_monitorobject_is_visible_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectconfig",
            name="monitor_plugin",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="monitor.monitorplugin",
                verbose_name="监控插件",
            ),
        ),
    ]
