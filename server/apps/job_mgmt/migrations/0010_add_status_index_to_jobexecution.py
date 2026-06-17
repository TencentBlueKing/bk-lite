"""Add db_index to JobExecution.status and composite index (scheduled_task, status)"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("job_mgmt", "0009_distributionfile_expire_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="jobexecution",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "等待中"),
                    ("running", "执行中"),
                    ("success", "成功"),
                    ("failed", "失败"),
                    ("timeout", "超时"),
                    ("cancelled", "已取消"),
                ],
                db_index=True,
                default="pending",
                max_length=32,
                verbose_name="执行状态",
            ),
        ),
        migrations.AddIndex(
            model_name="jobexecution",
            index=models.Index(
                fields=["scheduled_task", "status"],
                name="jobexec_task_status_idx",
            ),
        ),
    ]
