from django.db import models

from apps.core.models.time_info import TimeInfo


class CollectTaskCredentialHit(TimeInfo):
    STATUS_UNTESTED = "untested"
    STATUS_SUCCESS = "success"
    STATUS_KNOWN_FAILED = "known_failed"
    STATUS_CHOICES = (
        (STATUS_UNTESTED, "未探测"),
        (STATUS_SUCCESS, "成功"),
        (STATUS_KNOWN_FAILED, "已知失败"),
    )

    task = models.ForeignKey("CollectModels", on_delete=models.CASCADE, related_name="credential_hits")
    object_key = models.CharField(max_length=255)
    credential_id = models.CharField(max_length=64)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_UNTESTED)
    consecutive_failures = models.PositiveSmallIntegerField(default=0)
    cooldown_level = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    object_snapshot = models.JSONField(default=dict)

    class Meta:
        verbose_name = "采集任务凭据命中状态"
        verbose_name_plural = verbose_name
        unique_together = (("task", "object_key", "credential_id"),)
        indexes = [
            models.Index(fields=["task", "object_key"], name="cmdb_collect_hit_task_obj_idx"),
            models.Index(fields=["task", "status", "next_retry_at"], name="cmdb_collect_hit_retry_idx"),
        ]