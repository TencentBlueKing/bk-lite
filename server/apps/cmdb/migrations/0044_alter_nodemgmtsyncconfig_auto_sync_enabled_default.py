from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0043_node_mgmt_sync_snapshots"),
    ]

    operations = [
        migrations.AlterField(
            model_name="nodemgmtsyncconfig",
            name="auto_sync_enabled",
            field=models.BooleanField(default=False, verbose_name="是否自动同步"),
        ),
    ]
