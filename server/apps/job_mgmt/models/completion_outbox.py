"""作业终态副作用的持久化投递记录。"""

from django.db import models

from apps.core.models.time_info import TimeInfo


class JobCompletionOutbox(TimeInfo):
    """把终态写入与外部副作用拆成可恢复的 at-least-once 投递。"""

    class Kind(models.TextChoices):
        DONE_SENTINEL = "done_sentinel", "流结束哨兵"
        PLAYBOOK_CLEANUP = "playbook_cleanup", "Playbook 临时文件清理"
        WEB_CALLBACK = "web_callback", "HTTP 回调"
        NATS_CALLBACK = "nats_callback", "NATS 回调"

    class Status(models.TextChoices):
        PENDING = "pending", "待投递"
        DELIVERING = "delivering", "投递中"
        DELIVERED = "delivered", "已投递"
        FAILED = "failed", "投递失败"

    execution_id = models.BigIntegerField(db_index=True, verbose_name="作业执行 ID")
    kind = models.CharField(max_length=32, choices=Kind.choices, db_index=True, verbose_name="副作用类型")
    payload = models.JSONField(default=dict, verbose_name="不可变投递载荷")
    idempotency_key = models.CharField(max_length=255, unique=True, verbose_name="幂等键")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="投递状态",
    )
    attempts = models.PositiveIntegerField(default=0, verbose_name="尝试次数")
    max_attempts = models.PositiveIntegerField(default=12, verbose_name="单周期最大尝试次数")
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="下次重试时间")
    lease_token = models.UUIDField(null=True, blank=True, default=None, verbose_name="投递租约令牌")
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="投递租约到期时间")
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name="投递完成时间")
    last_error = models.TextField(blank=True, default="", verbose_name="最近错误")

    class Meta:
        db_table = "job_completion_outbox"
        verbose_name = "作业完成投递"
        verbose_name_plural = "作业完成投递"
        indexes = [
            models.Index(fields=["status", "next_retry_at"], name="job_outbox_retry_idx"),
            models.Index(fields=["status", "lease_expires_at"], name="job_outbox_lease_idx"),
        ]
