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


class MonitorPluginConfigTemplate(TimeInfo, MaintainerInfo):
    plugin = models.ForeignKey(MonitorPlugin, on_delete=models.CASCADE, verbose_name='监控插件')
    type = models.CharField(max_length=50, verbose_name='模板类型')
    config_type = models.CharField(max_length=50, default="", verbose_name='配置类型')
    file_type = models.CharField(max_length=50, default="", verbose_name='文件类型')
    content = models.TextField(verbose_name='模板内容')

    class Meta:
        verbose_name = '监控插件配置模板'
        verbose_name_plural = '监控插件配置模板'
        unique_together = ('plugin', 'type', 'config_type', 'file_type')


class MonitorPluginUITemplate(TimeInfo, MaintainerInfo):
    plugin = models.ForeignKey(MonitorPlugin, on_delete=models.CASCADE, verbose_name='监控插件')
    content = models.JSONField(default=dict, verbose_name='模版内容')

    class Meta:
        verbose_name = '监控插件UI模板'
        verbose_name_plural = '监控插件UI模板'
