from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0073_monitorevent_reassign_action"),
    ]

    operations = [
        migrations.AlterField(
            model_name="monitorevent",
            name="monitor_instance_id",
            field=models.CharField(db_index=True, max_length=200, verbose_name="监控对象实例ID"),
        ),
        migrations.AlterField(
            model_name="monitoralert",
            name="monitor_instance_id",
            field=models.CharField(db_index=True, default="", max_length=200, verbose_name="监控对象实例ID"),
        ),
        migrations.AlterField(
            model_name="monitoralert",
            name="monitor_instance_name",
            field=models.CharField(default="", max_length=200, verbose_name="监控对象实例名称"),
        ),
        migrations.AlterField(
            model_name="monitoralertmetricsnapshot",
            name="monitor_instance_id",
            field=models.CharField(db_index=True, max_length=200, verbose_name="监控对象实例ID"),
        ),
        migrations.AlterField(
            model_name="policyinstancebaseline",
            name="monitor_instance_id",
            field=models.CharField(db_index=True, max_length=200, verbose_name="监控实例ID"),
        ),
    ]
