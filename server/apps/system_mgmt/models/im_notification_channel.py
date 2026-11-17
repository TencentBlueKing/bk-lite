from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.core.utils.conditional_unique import ConditionalUniqueGuardQuerySet


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


class IMNotificationChannel(MaintainerInfo, TimeInfo):
    CHANNEL_TYPE = "im_notification"

    name = models.CharField(max_length=100)
    integration_instance = models.ForeignKey("system_mgmt.IntegrationInstance", on_delete=models.CASCADE, related_name="im_notification_channels")
    account_association = models.ForeignKey(
        "system_mgmt.IMAccountAssociation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="notification_channels",
    )
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=32, choices=IMNotificationChannelStatusChoices.choices, default=IMNotificationChannelStatusChoices.PENDING_SYNC
    )
    team = models.JSONField(default=list, blank=True)
    tags = models.ManyToManyField("system_mgmt.NotificationTag", blank=True, related_name="im_notification_channels")

    class Meta:
        ordering = ("name", "id")
        unique_together = ("name", "integration_instance")


class IMNotificationUserMapping(TimeInfo):
    account_association = models.ForeignKey("system_mgmt.IMAccountAssociation", on_delete=models.CASCADE, related_name="user_mappings")
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
            ("account_association", "user"),
            ("account_association", "external_identity_key", "external_identity_value"),
        )


class IMNotificationSyncRunQuerySet(ConditionalUniqueGuardQuerySet):
    guard_rules = {
        "status": (
            "running_guard",
            lambda status: True if status == IMNotificationSyncRunStatusChoices.RUNNING else None,
        )
    }


class IMNotificationSyncRun(TimeInfo):
    account_association = models.ForeignKey("system_mgmt.IMAccountAssociation", on_delete=models.CASCADE, related_name="sync_runs")
    trigger_mode = models.CharField(
        max_length=16,
        choices=IMNotificationTriggerModeChoices.choices,
        default=IMNotificationTriggerModeChoices.MANUAL,
    )
    status = models.CharField(
        max_length=32, choices=IMNotificationSyncRunStatusChoices.choices, default=IMNotificationSyncRunStatusChoices.RUNNING, db_index=True
    )
    summary = models.CharField(max_length=255, blank=True, default="")
    total_external_user_count = models.PositiveIntegerField(default=0)
    matched_count = models.PositiveIntegerField(default=0)
    unmatched_count = models.PositiveIntegerField(default=0)
    conflict_count = models.PositiveIntegerField(default=0)
    locked_config_snapshot = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    running_guard = models.BooleanField(null=True, default=None, editable=False)

    objects = IMNotificationSyncRunQuerySet.as_manager()

    class Meta:
        ordering = ("-started_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=["account_association"],
                condition=Q(status=IMNotificationSyncRunStatusChoices.RUNNING),
                name="unique_running_im_account_association_sync_run",
            ),
            models.UniqueConstraint(
                fields=["account_association", "running_guard"],
                name="uniq_im_sync_run_guard_per_account_association",
            ),
        ]

    def save(self, *args, **kwargs):
        self.running_guard = True if self.status == IMNotificationSyncRunStatusChoices.RUNNING else None
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "status" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"running_guard"}
        return super().save(*args, **kwargs)
