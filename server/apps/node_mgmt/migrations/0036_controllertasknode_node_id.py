from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0035_backfill_container_node_cpu_architecture"),
    ]

    operations = [
        migrations.AddField(
            model_name="controllertasknode",
            name="node_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100, verbose_name="节点ID"),
        ),
    ]
