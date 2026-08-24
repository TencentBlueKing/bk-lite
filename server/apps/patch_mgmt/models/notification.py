"""补丁周期评估通知投递记录。"""

from django.db import models

from apps.core.models.time_info import TimeInfo


class AssessmentNotificationDelivery(TimeInfo):
    """每次周期评估、每个通知渠道的持久投递意图。"""

    class Status(models.TextChoices):
        PENDING = "pending", "待投递"
        SENDING = "sending", "投递中"
        RETRY = "retry", "待重试"
        DELIVERED = "delivered", "已投递"
        FAILED = "failed", "投递失败"

    task = models.ForeignKey(
        "patch_mgmt.GovernanceTask",
        on_delete=models.CASCADE,
        related_name="notification_deliveries",
        verbose_name="周期评估任务",
    )
    channel_id = models.BigIntegerField(verbose_name="通知渠道ID")
    channel_name = models.CharField(max_length=128, blank=True, default="", verbose_name="通知渠道名称快照")
    channel_type = models.CharField(max_length=64, blank=True, default="", verbose_name="通知渠道类型快照")
    receivers = models.JSONField(default=list, verbose_name="接收人快照")
    team_id = models.BigIntegerField(verbose_name="通知组织ID快照")
    title = models.CharField(max_length=255, verbose_name="通知标题")
    content = models.TextField(verbose_name="通知正文")
    summary = models.JSONField(default=dict, verbose_name="评估汇总快照")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="投递状态",
    )
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name="已尝试次数")
    max_attempts = models.PositiveSmallIntegerField(default=3, verbose_name="最大尝试次数")
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="下次重试时间")
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name="投递完成时间")
    last_error = models.TextField(blank=True, default="", verbose_name="最后一次错误")
    claim_token = models.CharField(max_length=32, blank=True, default="", db_index=True, verbose_name="投递栅栏令牌")

    class Meta:
        db_table = "patch_assessment_notification_delivery"
        verbose_name = "周期评估通知投递"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["task", "channel_id"],
                name="patch_assess_notice_task_channel_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["status", "next_retry_at"],
                name="patch_assess_notice_retry_idx",
            )
        ]
