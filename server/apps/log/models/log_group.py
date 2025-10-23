from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from django.db import models


class LogGroup(TimeInfo, MaintainerInfo):
    id = models.CharField(primary_key=True, max_length=200, verbose_name='日志分组ID')
    name = models.CharField(max_length=200, verbose_name='日志分组名称')
    rule = models.JSONField(default=dict, verbose_name='规则')
    description = models.TextField(blank=True, verbose_name='描述')

    class Meta:
        verbose_name = '日志分组'
        verbose_name_plural = '日志分组'


class LogGroupOrganization(TimeInfo, MaintainerInfo):
    log_group = models.ForeignKey(LogGroup, on_delete=models.CASCADE, verbose_name='日志分组')
    organization = models.IntegerField(verbose_name='组织ID')

    class Meta:
        verbose_name = '日志分组组织'
        verbose_name_plural = '日志分组组织'
        unique_together = ('log_group', 'organization')


class SearchCondition(TimeInfo, MaintainerInfo):
    name = models.CharField(max_length=200, verbose_name='搜索条件名称')
    condition = models.JSONField(default=dict, verbose_name='搜索条件配置')
    organization = models.IntegerField(verbose_name='组织ID')

    class Meta:
        verbose_name = '搜索条件'
        verbose_name_plural = '搜索条件'
        ordering = ['-created_at']
