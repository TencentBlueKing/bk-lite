from django.conf import settings
from django.db import models

from apps.core.models.time_info import TimeInfo


class MonitorViewColumnPreference(TimeInfo):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="monitor_view_column_preferences",
        verbose_name="用户",
    )
    monitor_object = models.ForeignKey(
        "monitor.MonitorObject",
        on_delete=models.CASCADE,
        related_name="view_column_preferences",
        verbose_name="监控对象",
    )
    field_keys = models.JSONField(default=list, verbose_name="展示字段及顺序")

    class Meta:
        verbose_name = "监控视图个人列配置"
        verbose_name_plural = "监控视图个人列配置"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "monitor_object"],
                name="uniq_monitor_view_columns_user_object",
            )
        ]
