from django.db import models

from apps.core.models.time_info import TimeInfo


class AlertOutbox(TimeInfo):
    class Status(models.TextChoices):
        PENDING = "pending", "待投递"
        DELIVERING = "delivering", "投递中"
        DELIVERED = "delivered", "已投递"
        FAILED = "failed", "投递失败"

    kind = models.CharField(max_length=32, db_index=True)
    payload = models.JSONField(default=dict)
    idempotency_key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=8)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "alerts_outbox"
        indexes = [models.Index(fields=["status", "next_retry_at"], name="alert_outbox_retry_idx")]


class AlertNotificationDelivery(TimeInfo):
    """Alerts Outbox 中每个通知渠道的持久投递意图。"""

    class Status(models.TextChoices):
        PENDING = "pending", "待投递"
        DELIVERING = "delivering", "投递中"
        DELIVERED = "delivered", "已投递"
        FAILED = "failed", "投递失败"

    outbox = models.ForeignKey(
        AlertOutbox,
        on_delete=models.CASCADE,
        related_name="notification_deliveries",
    )
    position = models.PositiveIntegerField()
    delivery_key = models.CharField(max_length=64, unique=True)
    parameter = models.JSONField(default=dict)
    channel_id = models.CharField(max_length=128, blank=True, default="")
    channel_type = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=8)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    claim_token = models.CharField(max_length=32, blank=True, default="", db_index=True)

    class Meta:
        db_table = "alerts_notification_delivery"
        constraints = [
            models.UniqueConstraint(
                fields=["outbox", "position"],
                name="alerts_notice_outbox_position_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["status", "next_retry_at"],
                name="alerts_notice_retry_idx",
            ),
            models.Index(
                fields=["status", "updated_at"],
                name="alerts_notice_lease_idx",
            ),
        ]
