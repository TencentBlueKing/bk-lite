from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.monitor.models.monitor_object import MonitorObject


class MonitorPlugin(TimeInfo, MaintainerInfo):

    monitor_object = models.ManyToManyField(MonitorObject, verbose_name='监控对象')
    name = models.CharField(unique=True, max_length=100, verbose_name='插件名称')
    collector = models.CharField(max_length=100, default="", verbose_name='采集器名称')
    collect_type = models.CharField(max_length=50, default="", verbose_name='采集类型')
    description = models.TextField(blank=True, verbose_name='插件描述')

    class Meta:
        verbose_name = '监控插件'
        verbose_name_plural = '监控插件'
