from django.db import models

from apps.core.models.time_info import TimeInfo


class ActiveAlertFingerprint(TimeInfo):
    """跨数据库可用的活跃告警指纹租约。"""

    fingerprint = models.CharField(max_length=32, unique=True)
    alert = models.OneToOneField(
        "alerts.Alert",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="active_fingerprint_lease",
    )

    class Meta:
        db_table = "alerts_active_fingerprint"
