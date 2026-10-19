import uuid

from django.db import models
from django.db.models import JSONField

from apps.core.models.time_info import TimeInfo
from apps.module_link.constants import ITEM_STATUSES, TASK_STATUSES


class MonitorLinkTask(TimeInfo):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operator = models.CharField(max_length=128, default="")
    team = JSONField(default=list)
    status = models.CharField(max_length=32, default="waiting_access", db_index=True)
    summary = JSONField(default=dict)
    retain_until = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = "CMDB-监控同步任务"

    def save(self, *args, **kwargs):
        if self.status not in TASK_STATUSES:
            raise ValueError("invalid monitor link task status")
        super().save(*args, **kwargs)


class MonitorLinkTaskItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(MonitorLinkTask, on_delete=models.CASCADE, related_name="items")
    inst_uuid = models.CharField(max_length=64, db_index=True)
    model_id = models.CharField(max_length=128, default="")
    object_name = models.CharField(max_length=128, default="")
    inst_name = models.CharField(max_length=256, default="")
    ip = models.CharField(max_length=128, default="")
    port = models.CharField(max_length=32, default="")
    organization = JSONField(default=list)
    cloud_region_id = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=32, db_index=True)
    monitor_id = models.CharField(max_length=256, default="")

    class Meta:
        verbose_name = "CMDB-监控同步任务行"
        indexes = [models.Index(fields=["task", "status"])]

    def save(self, *args, **kwargs):
        if self.status not in ITEM_STATUSES:
            raise ValueError("invalid monitor link task item status")
        super().save(*args, **kwargs)


class MonitorAccessDraft(TimeInfo):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(MonitorLinkTask, on_delete=models.CASCADE, related_name="drafts")
    object_name = models.CharField(max_length=128)
    rows = JSONField(default=list)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = "监控接入草稿"
        unique_together = ("task", "object_name")


class ModuleLinkModelMap(TimeInfo):
    team = models.IntegerField(db_index=True)
    model_id = models.CharField(max_length=128)
    object_name = models.CharField(max_length=128)

    class Meta:
        verbose_name = "自定义模型到监控对象映射"
        unique_together = ("team", "model_id")
