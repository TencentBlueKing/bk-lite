from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0032_logextractor_grok_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="collectinstance",
            name="removed_collector_node_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100, verbose_name="已删除的采集节点ID"),
        ),
    ]
