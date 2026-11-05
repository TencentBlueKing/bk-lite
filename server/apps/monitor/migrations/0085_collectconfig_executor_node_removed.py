from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0084_remove_policygrouprule_push_alert_center"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectconfig",
            name="executor_node_id",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="已删除的采集节点ID"),
        ),
        migrations.AddField(
            model_name="collectconfig",
            name="executor_node_name",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="已删除的采集节点名称"),
        ),
        migrations.AddField(
            model_name="collectconfig",
            name="executor_node_removed",
            field=models.BooleanField(default=False, verbose_name="采集节点已删除"),
        ),
    ]
