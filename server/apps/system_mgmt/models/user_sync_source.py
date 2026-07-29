import json

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
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
    platform_config = models.JSONField(default=dict, blank=True)

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

    def build_schedule_spec(self):
        schedule_config = self.schedule_config or {}
        mode = schedule_config.get("mode")
        timezone_name = schedule_config.get("timezone") or timezone.get_current_timezone()

        if mode == "disabled" or not mode:
            return None

        if mode == "daily":
            hour, minute = map(int, str(schedule_config["time"]).split(":"))
            return {
                "kind": "crontab",
                "minute": str(minute),
                "hour": str(hour),
                "day_of_week": "*",
                "day_of_month": "*",
                "month_of_year": "*",
                "timezone": timezone_name,
            }

        if mode == "weekly":
            hour, minute = map(int, str(schedule_config["time"]).split(":"))
            weekdays = ",".join(str(day) for day in schedule_config["weekdays"])
            return {
                "kind": "crontab",
                "minute": str(minute),
                "hour": str(hour),
                "day_of_week": weekdays,
                "day_of_month": "*",
                "month_of_year": "*",
                "timezone": timezone_name,
            }

        if mode == "interval_hours":
            return {
                "kind": "crontab",
                "minute": "0",
                "hour": f"*/{schedule_config['interval_hours']}",
                "day_of_week": "*",
                "day_of_month": "*",
                "month_of_year": "*",
                "timezone": timezone_name,
            }

        raise ValueError(f"Unsupported user sync schedule mode: {mode}")

    def create_sync_periodic_task(self):
        schedule_spec = self.build_schedule_spec()
        if schedule_spec is None:
            return
        task_args = json.dumps([self.id, UserSyncTriggerModeChoices.SCHEDULE], separators=(",", ":"))
        task_path = "apps.system_mgmt.tasks.execute_user_sync_source"
        self.create_periodic_task_from_spec(schedule_spec, self.periodic_task_name(), task_args, task_path)

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
        constraints = [
            models.UniqueConstraint(
                fields=["source"],
                condition=Q(status=UserSyncRunStatusChoices.RUNNING),
                name="unique_running_user_sync_run_per_source",
            )
        ]


def instance_id_or_none(instance):
    return getattr(instance, "id", None)
