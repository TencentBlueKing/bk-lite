from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("job_mgmt", "0019_template_revision"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobexecution",
            name="async_callback_context",
            field=models.JSONField(blank=True, default=None, null=True, verbose_name="通用异步回调上下文"),
        ),
        migrations.AddField(
            model_name="jobexecution",
            name="async_callback_deadline_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="异步回调截止时间"),
        ),
        migrations.AddField(
            model_name="jobexecution",
            name="async_callback_key",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True, verbose_name="异步回调令牌摘要"),
        ),
        migrations.AlterField(
            model_name="jobcompletionoutbox",
            name="kind",
            field=models.CharField(
                choices=[
                    ("done_sentinel", "流结束哨兵"),
                    ("playbook_cleanup", "Playbook 临时文件清理"),
                    ("web_callback", "HTTP 回调"),
                    ("nats_callback", "NATS 回调"),
                    ("async_callback", "通用异步回调"),
                ],
                db_index=True,
                max_length=32,
                verbose_name="副作用类型",
            ),
        ),
        migrations.AlterField(
            model_name="jobcompletionoutbox",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "待投递"),
                    ("delivering", "投递中"),
                    ("delivered", "已投递"),
                    ("failed", "投递失败"),
                    ("stopped", "停止投递"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
                verbose_name="投递状态",
            ),
        ),
    ]
