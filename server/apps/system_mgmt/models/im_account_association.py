from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.mixinx import PeriodicTaskUtils
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.system_mgmt.models.im_notification_channel import IMNotificationExternalFieldChoices, IMNotificationMappingStrategyChoices


class IMAccountAssociationStatusChoices(models.TextChoices):
    PENDING_SYNC = "pending_sync", _("Pending Sync")
    READY = "ready", _("Ready")
    NEEDS_RESYNC = "needs_resync", _("Needs Resync")


class IMAccountAssociation(MaintainerInfo, TimeInfo, PeriodicTaskUtils):
    name = models.CharField(max_length=100)
    integration_instance = models.ForeignKey(
        "system_mgmt.IntegrationInstance",
        on_delete=models.CASCADE,
        related_name="account_associations",
    )
    platform_match_field = models.CharField(
        max_length=32,
        choices=IMNotificationMappingStrategyChoices.choices,
        default=IMNotificationMappingStrategyChoices.EMAIL,
    )
    external_match_field = models.CharField(max_length=64, default=IMNotificationExternalFieldChoices.EMAIL)
    external_receive_field = models.CharField(max_length=64, default=IMNotificationExternalFieldChoices.USER_ID)
    schedule_config = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=32,
        choices=IMAccountAssociationStatusChoices.choices,
        default=IMAccountAssociationStatusChoices.PENDING_SYNC,
    )

    class Meta:
        ordering = ("name", "id")
        unique_together = ("name", "integration_instance")

    def periodic_task_name(self):
        return f"im_account_association_{self.id}"

    def create_sync_periodic_task(self):
        sync_time = (self.schedule_config or {}).get("sync_time", "00:00")
        self.create_periodic_task(
            sync_time,
            self.periodic_task_name(),
            f"[{self.id}]",
            "apps.system_mgmt.tasks.schedule_im_account_association_sync",
        )

    def delete_sync_periodic_task(self):
        self.delete_periodic_task(self.periodic_task_name())
