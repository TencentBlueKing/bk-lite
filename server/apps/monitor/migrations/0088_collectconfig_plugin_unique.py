from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0087_collectconfig_executor_node_id_index"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="collectconfig",
            unique_together={("monitor_instance", "collector", "collect_type", "config_type", "monitor_plugin")},
        ),
    ]
