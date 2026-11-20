from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0086_policy_instance_baseline_dimensions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="collectconfig",
            name="executor_node_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100, verbose_name="已删除的采集节点ID"),
        ),
    ]
