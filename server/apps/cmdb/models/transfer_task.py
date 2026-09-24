import uuid

from django.db import models
from django.utils.timezone import now


class CmdbTransferTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey("system_mgmt.User", on_delete=models.PROTECT)
    kind = models.CharField(max_length=8)
    model_id = models.CharField(max_length=128)
    model_name = models.CharField(max_length=128, default="")
    team_id = models.IntegerField()
    include_children = models.BooleanField(default=False)
    params = models.JSONField(default=dict)
    authorization = models.JSONField(default=dict)
    schema_hash = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=24, default="queued")
    phase = models.CharField(max_length=32, default="queued")
    processed_rows = models.PositiveIntegerField(default=0)
    total_rows = models.PositiveIntegerField(null=True)
    summary = models.JSONField(default=dict)
    error_code = models.CharField(max_length=64, default="")
    message = models.CharField(max_length=512, default="")
    source_key = models.CharField(max_length=512, default="")
    source_hash = models.CharField(max_length=64, default="")
    filename = models.CharField(max_length=255, default="")
    artifacts = models.JSONField(default=dict)
    execution_token = models.CharField(max_length=32, default="")
    holds_slot = models.BooleanField(default=False, db_index=True)
    lease_expires_at = models.DateTimeField(null=True)
    deadline_at = models.DateTimeField(null=True)
    dispatched_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(default=now)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    expires_at = models.DateTimeField(db_index=True)
    delete_pending = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "idempotency_key"], name="cmdb_transfer_request_key")]
        indexes = [
            models.Index(fields=["owner", "created_at"], name="cmdb_transfer_owner_date"),
            models.Index(fields=["status", "lease_expires_at"], name="cmdb_transfer_state_lease"),
        ]


class CmdbTransferGuard(models.Model):
    """跨 Worker 领取使用固定行锁；游标只用于有界孤儿扫描。"""

    key = models.CharField(primary_key=True, max_length=32)
    cursor = models.CharField(max_length=512, default="")
