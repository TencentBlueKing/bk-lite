from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class NotificationTag(MaintainerInfo, TimeInfo):
    """通知渠道共用的标签候选。一行是一对 key 与 value，不按组织拆分。"""

    key = models.CharField(max_length=64)
    value = models.CharField(max_length=64)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(fields=["key", "value"], name="uniq_notification_tag_key_value"),
        ]
