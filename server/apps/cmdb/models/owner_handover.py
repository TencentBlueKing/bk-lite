import uuid

from django.db import models
from django.utils.timezone import now

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
PARTIAL_FAILED = "partial_failed"
FAILED = "failed"
CANCELLED = "cancelled"

ACTIVE_STATUSES = (QUEUED, RUNNING)
TERMINAL_STATUSES = (SUCCEEDED, PARTIAL_FAILED, FAILED, CANCELLED)

OUTCOME_SUCCESS = "success"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"


class OwnerHandoverTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operator_username = models.CharField(max_length=150)
    operator_domain = models.CharField(max_length=100, default="domain.com")
    from_user_id = models.IntegerField()
    to_user_id = models.IntegerField()
    from_label = models.CharField(max_length=255, default="")
    to_label = models.CharField(max_length=255, default="")
    attr_id = models.CharField(max_length=128, default="")
    attr_name = models.CharField(max_length=255, default="")
    model_ids = models.JSONField(default=list)
    team_id = models.IntegerField()
    include_children = models.BooleanField(default=False)
    authorization = models.JSONField(default=dict)
    status = models.CharField(max_length=32, default=QUEUED)
    execution_token = models.CharField(max_length=32)
    idempotency_key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    cancel_requested = models.BooleanField(default=False)
    total_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    message = models.CharField(max_length=512, default="")
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["operator_username", "operator_domain", "idempotency_key"],
                name="cmdb_owner_handover_idempotency",
            )
        ]
        indexes = [
            models.Index(fields=["from_user_id", "status"], name="cmdb_handover_from_status"),
            models.Index(fields=["operator_username", "operator_domain", "created_at"], name="cmdb_handover_operator_date"),
        ]


class OwnerHandoverFailure(models.Model):
    task = models.ForeignKey(OwnerHandoverTask, on_delete=models.CASCADE, related_name="failures")
    model_id = models.CharField(max_length=128, default="")
    model_name = models.CharField(max_length=128, default="")
    inst_uuid = models.CharField(max_length=64, default="")
    inst_name = models.CharField(max_length=255, default="")
    reason_code = models.CharField(max_length=64)
    message = models.CharField(max_length=200, default="")

    class Meta:
        indexes = [models.Index(fields=["task", "id"], name="cmdb_handover_failure_task")]


class OwnerHandoverOutcome(models.Model):
    task = models.ForeignKey(OwnerHandoverTask, on_delete=models.CASCADE, related_name="outcomes")
    inst_uuid = models.CharField(max_length=64)
    result = models.CharField(max_length=16)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["task", "inst_uuid"], name="cmdb_owner_handover_outcome")]
