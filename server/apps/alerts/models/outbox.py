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
