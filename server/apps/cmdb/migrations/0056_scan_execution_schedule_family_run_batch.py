from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0055_firstcollectionrun_lock_retries"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanexecution",
            name="schedule",
            field=models.JSONField(default=dict, help_text="JOB 工作队列：切批、游标与当前批次截止"),
        ),
        migrations.AddField(
            model_name="scanfamilyrun",
            name="batch_index",
            field=models.PositiveSmallIntegerField(default=0, help_text="同模型 JOB 切批序号"),
        ),
        migrations.AlterUniqueTogether(
            name="scanfamilyrun",
            unique_together={("execution", "model_id", "driver_type", "batch_index")},
        ),
    ]
