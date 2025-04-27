from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class MonitorObject(TimeInfo, MaintainerInfo):
    LEVEL_CHOICES = [('base', 'Base'), ('derivative', 'Derivative')]

    name = models.CharField(unique=True, max_length=100, verbose_name='监控对象')
    type = models.CharField(max_length=50, verbose_name='监控对象类型')
    level = models.CharField(default="base", max_length=50, verbose_name='监控对象级别')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', verbose_name='父级监控对象')
    description = models.TextField(blank=True, verbose_name='监控对象描述')

    class Meta:
        verbose_name = '监控对象'
        verbose_name_plural = '监控对象'


class MonitorInstance(TimeInfo, MaintainerInfo):
    id = models.CharField(primary_key=True, max_length=200, verbose_name='监控对象实例ID')
    name = models.CharField(db_index=True, max_length=200, default="", verbose_name='监控对象实例名称')
    interval = models.IntegerField(default=10, verbose_name='监控实例采集间隔(s)')
    monitor_object = models.ForeignKey(MonitorObject, on_delete=models.CASCADE, verbose_name='监控对象')
    auto = models.BooleanField(default=False, verbose_name='是否自动发现')
    is_deleted = models.BooleanField(db_index=True, default=False, verbose_name='是否删除')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = '监控对象实例'
        verbose_name_plural = '监控对象实例'


class MonitorInstanceOrganization(TimeInfo, MaintainerInfo):
    monitor_instance = models.ForeignKey(MonitorInstance, on_delete=models.CASCADE, verbose_name='监控对象实例')
    organization = models.CharField(max_length=100, verbose_name='组织id')

    class Meta:
        verbose_name = '监控对象实例组织'
        verbose_name_plural = '监控对象实例组织'
        unique_together = ('monitor_instance', 'organization')


class MonitorInstanceGroupingRule(TimeInfo, MaintainerInfo):

    SELECT = 'select'
    CONDITION = 'condition'
    RULE_TYPE_CHOICES = (
        (SELECT, 'Select'),
        (CONDITION, 'Condition'),
    )

    monitor_object = models.ForeignKey(MonitorObject, on_delete=models.CASCADE, verbose_name='监控对象')
    name = models.CharField(max_length=100, verbose_name='分组规则名称')
    type = models.CharField(max_length=30, choices=RULE_TYPE_CHOICES, verbose_name='分组规则类型')
    organizations = models.JSONField(default=list, verbose_name='所属组织')
    grouping_rules = models.JSONField(default=dict, verbose_name='分组规则详情')


    class Meta:
        verbose_name = '监控实例分组规则'
        verbose_name_plural = '监控实例分组规则'