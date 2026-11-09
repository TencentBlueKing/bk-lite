from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowexecution",
            name="async_callback_context",
            field=models.JSONField(blank=True, default=None, null=True, verbose_name="通用异步回调上下文"),
        ),
        migrations.AddField(
            model_name="workflowexecution",
            name="async_callback_deadline_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="异步回调截止时间"),
        ),
        migrations.AddField(
            model_name="workflowexecution",
            name="async_callback_key",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True, verbose_name="异步回调令牌摘要"),
        ),
        migrations.CreateModel(
            name="WorkflowCompletionOutbox",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("execution_id", models.UUIDField(db_index=True, verbose_name="编排执行 ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[("async_callback", "通用异步回调")],
                        db_index=True,
                        max_length=32,
                        verbose_name="副作用类型",
                    ),
                ),
                ("payload", models.JSONField(default=dict, verbose_name="不可变投递载荷")),
                ("idempotency_key", models.CharField(max_length=255, unique=True, verbose_name="幂等键")),
                (
                    "status",
                    models.CharField(
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
                ("attempts", models.PositiveIntegerField(default=0, verbose_name="尝试次数")),
                ("max_attempts", models.PositiveIntegerField(default=12, verbose_name="单周期最大尝试次数")),
                ("next_retry_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="下次重试时间")),
                ("lease_token", models.UUIDField(blank=True, default=None, null=True, verbose_name="投递租约令牌")),
                ("lease_expires_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="投递租约到期时间")),
                ("delivered_at", models.DateTimeField(blank=True, null=True, verbose_name="投递完成时间")),
                ("last_error", models.TextField(blank=True, default="", verbose_name="最近错误")),
            ],
            options={
                "verbose_name": "编排完成投递",
                "verbose_name_plural": "编排完成投递",
                "db_table": "workflow_completion_outbox",
            },
        ),
        migrations.AddIndex(
            model_name="workflowcompletionoutbox",
            index=models.Index(fields=["status", "next_retry_at"], name="wf_outbox_retry_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowcompletionoutbox",
            index=models.Index(fields=["status", "lease_expires_at"], name="wf_outbox_lease_idx"),
        ),
    ]
