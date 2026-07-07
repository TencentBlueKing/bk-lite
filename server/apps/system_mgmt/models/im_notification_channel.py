from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.mixinx import PeriodicTaskUtils
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class IMNotificationMappingStrategyChoices(models.TextChoices):
    USERNAME = "username", _("Platform Username")
    EMAIL = "email", _("Platform Email")
    PHONE = "phone", _("Platform Mobile")


class IMNotificationExternalFieldChoices(models.TextChoices):
    USER_ID = "user_id", _("Feishu User ID")
    OPEN_ID = "open_id", _("Feishu Open ID")
    EMAIL = "email", _("Feishu Email")
    MOBILE = "mobile", _("Feishu Mobile")


class IMNotificationMappingStatusChoices(models.TextChoices):
    MATCHED = "matched", _("Matched")
    UNMATCHED = "unmatched", _("Unmatched")
    ERROR = "error", _("Error")


class IMNotificationTriggerModeChoices(models.TextChoices):
    MANUAL = "manual", _("Manual")
    SCHEDULE = "schedule", _("Schedule")


class IMNotificationChannelStatusChoices(models.TextChoices):
    PENDING_SYNC = "pending_sync", _("Pending Sync")
    READY = "ready", _("Ready")
    NEEDS_RESYNC = "needs_resync", _("Needs Resync")
    DISABLED = "disabled", _("Disabled")


class IMNotificationSyncRunStatusChoices(models.TextChoices):
    RUNNING = "running", _("Running")
    SUCCESS = "success", _("Success")
    PARTIAL = "partial", _("Partial Success")
    FAILED = "failed", _("Failed")


class IMNotificationChannel(MaintainerInfo, TimeInfo, PeriodicTaskUtils):
    name = models.CharField(max_length=100)
    integration_instance = models.ForeignKey("system_mgmt.IntegrationInstance", on_delete=models.CASCADE, related_name="im_notification_channels")
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=32, choices=IMNotificationChannelStatusChoices.choices, default=IMNotificationChannelStatusChoices.PENDING_SYNC)
    platform_match_field = models.CharField(max_length=32, choices=IMNotificationMappingStrategyChoices.choices, default=IMNotificationMappingStrategyChoices.EMAIL)
    external_match_field = models.CharField(max_length=64, default=IMNotificationExternalFieldChoices.EMAIL)
    external_receive_field = models.CharField(max_length=64, default=IMNotificationExternalFieldChoices.USER_ID)
    schedule_config = models.JSONField(default=dict, blank=True)
    team = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("name", "id")
        unique_together = ("name", "integration_instance")

    def periodic_task_name(self):
        return f"im_notification_channel_{self.id}"

    def create_sync_periodic_task(self):
        sync_time = (self.schedule_config or {}).get("sync_time", "00:00")
        task_args = f"[{self.id}]"
        task_path = "apps.system_mgmt.tasks.schedule_im_notification_sync"
        self.create_periodic_task(sync_time, self.periodic_task_name(), task_args, task_path)

    def delete_sync_periodic_task(self):
        self.delete_periodic_task(self.periodic_task_name())


class IMNotificationUserMapping(TimeInfo):
    channel = models.ForeignKey("system_mgmt.IMNotificationChannel", on_delete=models.CASCADE, related_name="user_mappings")
    user = models.ForeignKey("system_mgmt.User", on_delete=models.CASCADE, related_name="im_notification_mappings")
    external_identity_key = models.CharField(max_length=64)
    external_identity_value = models.CharField(max_length=255)
    external_receive_key = models.CharField(max_length=64)
    external_display_name = models.CharField(max_length=150, blank=True, default="")
    match_context = models.JSONField(default=dict, blank=True)
    external_snapshot = models.JSONField(default=dict, blank=True)
    synced_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-synced_at", "-id")
        unique_together = (
            ("channel", "user"),
            ("channel", "external_identity_key", "external_identity_value"),
        )


class IMNotificationSyncRun(TimeInfo):
    channel = models.ForeignKey("system_mgmt.IMNotificationChannel", on_delete=models.CASCADE, related_name="sync_runs")
    trigger_mode = models.CharField(
        max_length=16,
        choices=IMNotificationTriggerModeChoices.choices,
        default=IMNotificationTriggerModeChoices.MANUAL,
    )
    status = models.CharField(max_length=32, choices=IMNotificationSyncRunStatusChoices.choices, default=IMNotificationSyncRunStatusChoices.RUNNING, db_index=True)
    summary = models.CharField(max_length=255, blank=True, default="")
    total_external_user_count = models.PositiveIntegerField(default=0)
    matched_count = models.PositiveIntegerField(default=0)
    unmatched_count = models.PositiveIntegerField(default=0)
    conflict_count = models.PositiveIntegerField(default=0)
    locked_config_snapshot = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=["channel"],
                condition=Q(status=IMNotificationSyncRunStatusChoices.RUNNING),
                name="unique_running_im_notification_sync_run_per_channel",
            )
        ]
