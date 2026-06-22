from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.mixinx import PeriodicTaskUtils
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo

class UserSyncTriggerModeChoices(models.TextChoices):
    MANUAL = "manual", _("Manual")
    SCHEDULE = "schedule", _("Schedule")


class UserSyncRunStatusChoices(models.TextChoices):
    RUNNING = "running", _("Running")
    SUCCESS = "success", _("Success")
    FAILED = "failed", _("Failed")
    PARTIAL = "partial", _("Partial Success")


class UserSyncSource(MaintainerInfo, TimeInfo, PeriodicTaskUtils):
    name = models.CharField(max_length=100)
    integration_instance = models.ForeignKey("system_mgmt.IntegrationInstance", on_delete=models.CASCADE, related_name="user_sync_sources")
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")
    root_group_name = models.CharField(max_length=100)
    field_mapping = models.JSONField(default=dict, blank=True)
    schedule_config = models.JSONField(default=dict, blank=True)
    business_config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name", "id")
        unique_together = ("name", "integration_instance")

    def clean(self):
        instance = self.integration_instance
        if not instance_id_or_none(instance):
            return
        if not instance.enabled or instance.status != "ready" or instance.capability_status.get("user_sync") != "ready":
            raise ValidationError({"integration_instance": "Integration instance user_sync capability is not ready"})

    def periodic_task_name(self):
        return f"user_sync_source_{self.id}"

    def create_sync_periodic_task(self):
        sync_time = (self.schedule_config or {}).get("sync_time", "00:00")
        task_args = f"[{self.id}, \"{UserSyncTriggerModeChoices.SCHEDULE}\"]"
        task_path = "apps.system_mgmt.tasks.execute_user_sync_source"
        self.create_periodic_task(sync_time, self.periodic_task_name(), task_args, task_path)

    def delete_sync_periodic_task(self):
        self.delete_periodic_task(self.periodic_task_name())


class UserSyncRun(TimeInfo):
    source = models.ForeignKey("system_mgmt.UserSyncSource", on_delete=models.CASCADE, related_name="runs")
    trigger_mode = models.CharField(max_length=16, choices=UserSyncTriggerModeChoices.choices, default=UserSyncTriggerModeChoices.MANUAL)
    status = models.CharField(max_length=16, choices=UserSyncRunStatusChoices.choices, default=UserSyncRunStatusChoices.RUNNING, db_index=True)
    request_id = models.CharField(max_length=64, blank=True, default="")
    summary = models.CharField(max_length=255, blank=True, default="")
    synced_user_count = models.PositiveIntegerField(default=0)
    synced_group_count = models.PositiveIntegerField(default=0)
    disabled_user_count = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at", "-id")


def instance_id_or_none(instance):
    return getattr(instance, "id", None)
