from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("monitor", "0056_alter_monitorobject_cleanup_timeout_unit")]

    operations = [
        migrations.AddField(
            model_name="monitorinstance",
            name="node_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=100,
                null=True,
                unique=True,
                verbose_name="关联节点ID",
            ),
        ),
        migrations.AddField(
            model_name="monitorinstance",
            name="cmdb_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=100,
                null=True,
                unique=True,
                verbose_name="关联CMDB实例ID",
            ),
        ),
    ]
