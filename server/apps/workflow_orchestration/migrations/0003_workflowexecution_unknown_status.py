from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflow_orchestration", "0002_workflow_is_builtin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workflowexecution",
            name="status",
            field=models.CharField(
                choices=[
                    ("QUEUED", "排队中"),
                    ("RUNNING", "执行中"),
                    ("WAITING_APPROVAL", "等待审批"),
                    ("TERMINATING", "终止中"),
                    ("UNKNOWN", "结果未知"),
                    ("SUCCEEDED", "成功"),
                    ("FAILED", "失败"),
                    ("TIMED_OUT", "已超时"),
                    ("TERMINATED", "已终止"),
                ],
                db_index=True,
                default="QUEUED",
                max_length=32,
            ),
        ),
    ]
