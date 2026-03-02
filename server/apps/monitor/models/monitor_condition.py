from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.monitor.models.monitor_object import MonitorObject


class MonitorCondition(TimeInfo, MaintainerInfo):
    """监控条件"""

    name = models.CharField(max_length=200, verbose_name="条件名称")
    description = models.TextField(blank=True, default="", verbose_name="条件描述")
    condition = models.JSONField(default=dict, verbose_name="条件配置")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    monitor_object = models.ForeignKey(
        MonitorObject, on_delete=models.CASCADE, verbose_name="监控对象", null=True
    )

    class Meta:
        verbose_name = "监控条件"
        verbose_name_plural = "监控条件"
        ordering = ["-created_at"]


class MonitorConditionOrganization(TimeInfo, MaintainerInfo):
    """监控条件与组织的关联表"""

    monitor_condition = models.ForeignKey(
        MonitorCondition,
        on_delete=models.CASCADE,
        related_name="organizations",
        verbose_name="监控条件",
    )
    organization = models.IntegerField(verbose_name="组织ID")

    class Meta:
        verbose_name = "监控条件组织"
        verbose_name_plural = "监控条件组织"
        unique_together = ("monitor_condition", "organization")
