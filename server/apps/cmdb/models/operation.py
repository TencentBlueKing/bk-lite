import uuid

from django.db import models

from apps.core.models.time_info import TimeInfo


class CmdbOperationStatus(models.TextChoices):
    PENDING = "pending", "等待图写"
    GRAPH_WRITING = "graph_writing", "图写执行中"
    GRAPH_COMMITTED = "graph_committed", "图写已提交"
    COMPLETED = "completed", "已完成"
    ERROR = "error", "失败"


class CmdbOperationOutboxStatus(models.TextChoices):
    PENDING = "pending", "等待投递"
    SENDING = "sending", "投递中"
    RETRY = "retry", "等待重试"
    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"


class CmdbOperation(TimeInfo):
    operation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    operator = models.CharField(max_length=128)
    idempotency_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    action = models.CharField(max_length=64)
    target = models.JSONField(default=dict, blank=True)
    request_snapshot = models.JSONField(default=dict, blank=True)
    result_snapshot = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=32,
        choices=CmdbOperationStatus.choices,
        default=CmdbOperationStatus.PENDING,
    )
    last_error = models.TextField(blank=True, default="")
    owner_token = models.CharField(max_length=64, blank=True, default="")
    lease_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "cmdb_operation"
        constraints = [
            models.UniqueConstraint(
                fields=["operator", "idempotency_key"],
                name="uniq_cmdb_operation_idempotency",
            )
        ]
        indexes = [models.Index(fields=["status", "lease_expires_at"], name="cmdb_operation_status_idx")]


class CmdbOperationOutbox(TimeInfo):
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    operation = models.ForeignKey(CmdbOperation, on_delete=models.CASCADE, related_name="outbox_events")
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16,
        choices=CmdbOperationOutboxStatus.choices,
        default=CmdbOperationOutboxStatus.PENDING,
    )
    owner_token = models.CharField(max_length=64, blank=True, default="")
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "cmdb_operation_outbox"
        constraints = [
            models.UniqueConstraint(
                fields=["operation", "event_type"],
                name="uniq_cmdb_operation_event",
            )
        ]
        indexes = [models.Index(fields=["status", "lease_expires_at"], name="cmdb_op_outbox_lease_idx")]
