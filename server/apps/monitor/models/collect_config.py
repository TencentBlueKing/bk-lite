from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.monitor.models.monitor_object import MonitorInstance
from apps.monitor.models.plugin import MonitorPlugin


class CollectConfig(TimeInfo, MaintainerInfo):
    id = models.CharField(primary_key=True, max_length=100, verbose_name="配置ID")
    monitor_instance = models.ForeignKey(MonitorInstance, on_delete=models.CASCADE, verbose_name="监控对象实例")
    monitor_plugin = models.ForeignKey(MonitorPlugin, blank=True, null=True, on_delete=models.CASCADE, verbose_name="监控插件")
    collector = models.CharField(max_length=100, verbose_name="采集器名称")
    collect_type = models.CharField(max_length=50, verbose_name="采集类型")
    config_type = models.CharField(max_length=50, verbose_name="配置类型")
    file_type = models.CharField(max_length=50, verbose_name="文件类型")
    is_child = models.BooleanField(default=True, verbose_name="是否子配置")

    class Meta:
        verbose_name = "采集配置"
        verbose_name_plural = "采集配置"
        unique_together = ("monitor_instance", "collector", "collect_type", "config_type")
