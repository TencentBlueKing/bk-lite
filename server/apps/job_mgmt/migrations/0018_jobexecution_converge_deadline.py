from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("job_mgmt", "0017_targetteammembership")]

    operations = [
        migrations.AddField(
            model_name="jobexecution",
            name="converge_deadline_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="执行状态收敛截止时间"),
        ),
        migrations.AlterField(
            model_name="jobexecution",
            name="terminal_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ansible_callback", "Ansible 真实回调"),
                    ("cancel_timeout", "取消超时兜底"),
                    ("execution_timeout", "执行超时兜底"),
                    ("dispatch_timeout", "调度超时兜底"),
                ],
                default="",
                max_length=32,
                null=True,
                verbose_name="终态写入来源",
            ),
        ),
        migrations.AddIndex(
            model_name="jobexecution",
            index=models.Index(fields=["status", "converge_deadline_at"], name="jobexec_status_deadline_idx"),
        ),
    ]
