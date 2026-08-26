from django.db import models

from apps.core.models.time_info import TimeInfo


class ExternalResourceCleanupIntent(TimeInfo):
    class ResourceType(models.TextChoices):
        MLFLOW_EXPERIMENT_MODEL = "mlflow_experiment_model", "MLflow experiment and model"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    idempotency_key = models.CharField(max_length=64, unique=True)
    resource_type = models.CharField(max_length=64, choices=ResourceType.choices, db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    claim_token = models.CharField(max_length=64, blank=True, default="")
    claim_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error = models.TextField(blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "mlops_external_resource_cleanup_intent"
        indexes = [
            models.Index(fields=["status", "next_retry_at"], name="mlops_ext_cleanup_due_idx"),
        ]
