from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0033_alter_monitoralertmetricsnapshot_snapshots"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorplugin",
            name="node_selector",
            field=models.JSONField(blank=True, default=dict, verbose_name="节点选择约束"),
        ),
    ]
