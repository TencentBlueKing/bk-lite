from django.db import models
from django.db.models import JSONField

from apps.core.models.time_info import TimeInfo


class FirstCollectionRun(TimeInfo):
    STATUS_WAITING_CONFIG = "waiting_config"
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_RETRY_WAIT = "retry_wait"
    STATUS_ACCEPTED = "accepted"
    STATUS_PARTIAL = "partial"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = (
        (STATUS_WAITING_CONFIG, "等待配置"),
        (STATUS_PENDING, "待触发"),
        (STATUS_RUNNING, "触发中"),
        (STATUS_RETRY_WAIT, "等待重试"),
        (STATUS_ACCEPTED, "已接纳"),
        (STATUS_PARTIAL, "部分接纳"),
        (STATUS_FAILED, "触发失败"),
        (STATUS_SKIPPED, "已跳过"),
    )

    collect_task = models.ForeignKey(
        "CollectModels",
        null=True,
        blank=True,
        related_name="first_collection_runs",
        on_delete=models.SET_NULL,
    )
    fingerprint = models.CharField(max_length=64)
    task_revision = models.DateTimeField()
    reason = models.CharField(max_length=255, default="create")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_WAITING_CONFIG)
    config_attempt = models.PositiveSmallIntegerField(default=0)
    dispatch_attempt = models.PositiveSmallIntegerField(default=0)
    attempt = models.PositiveSmallIntegerField(default=0)
    claim_token = models.CharField(max_length=64, blank=True, default="")
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    channel_results = JSONField(default=dict)
    failed_stage = models.CharField(max_length=64, blank=True, default="")
    error_type = models.CharField(max_length=128, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("collect_task", "fingerprint", "task_revision"),
                name="cmdb_first_collect_task_revision_uniq",
            ),
        )
        indexes = (models.Index(fields=("status", "updated_at"), name="cmdb_first_collect_status_idx"),)
