from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0030_alter_event_action"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectinstance",
            name="collector_node_removed",
            field=models.BooleanField(default=False, verbose_name="采集节点已删除"),
        ),
        migrations.AddField(
            model_name="collectinstance",
            name="removed_collector_node_id",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="已删除的采集节点ID"),
        ),
        migrations.AddField(
            model_name="collectinstance",
            name="removed_collector_node_name",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="已删除的采集节点名称"),
        ),
    ]
