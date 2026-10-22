import uuid

from django.db import models
from django.db.models import JSONField

from apps.core.models.time_info import TimeInfo
from apps.module_link.constants import ITEM_STATUSES, REVERSE_ITEM_STATUSES, REVERSE_TASK_STATUSES, TASK_STATUSES


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
    message = models.CharField(max_length=512, blank=True, default="")

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


class MonitorCmdbTask(TimeInfo):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operator = models.CharField(max_length=128, default="")
    team = JSONField(default=list)
    object_name = models.CharField(max_length=128, default="")
    status = models.CharField(max_length=32, default="waiting_create", db_index=True)
    summary = JSONField(default=dict)
    retain_until = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = "监控-CMDB同步任务"

    def save(self, *args, **kwargs):
        if self.status not in REVERSE_TASK_STATUSES:
            raise ValueError("invalid monitor cmdb task status")
        super().save(*args, **kwargs)


class MonitorCmdbTaskItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(MonitorCmdbTask, on_delete=models.CASCADE, related_name="items")
    monitor_id = models.CharField(max_length=256, db_index=True)
    object_name = models.CharField(max_length=128, default="")
    model_id = models.CharField(max_length=128, default="")
    inst_name = models.CharField(max_length=256, default="")
    ip = models.CharField(max_length=128, default="")
    organization = JSONField(default=list)
    cloud_region_id = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=32, db_index=True)
    cmdb_id = models.CharField(max_length=64, default="")
    message = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        verbose_name = "监控-CMDB同步任务行"
        indexes = [models.Index(fields=["task", "status"], name="module_link_task_id_rev_idx")]

    def save(self, *args, **kwargs):
        if self.status not in REVERSE_ITEM_STATUSES:
            raise ValueError("invalid monitor cmdb task item status")
        super().save(*args, **kwargs)
