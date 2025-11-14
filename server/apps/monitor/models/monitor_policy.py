from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.monitor.models import MonitorPlugin
from apps.monitor.models.monitor_object import MonitorObject


class PolicyTemplate(models.Model):
    monitor_object = models.ForeignKey(MonitorObject, on_delete=models.CASCADE, verbose_name='监控对象')
    plugin = models.ForeignKey(MonitorPlugin, on_delete=models.CASCADE, verbose_name='监控插件')
    templates = models.JSONField(default=list, verbose_name='策略模板列表')

    class Meta:
        verbose_name = '监控策略模板'
        verbose_name_plural = '监控策略模板'
        unique_together = ('monitor_object', 'plugin')


class MonitorPolicy(TimeInfo, MaintainerInfo):

    monitor_object = models.ForeignKey(MonitorObject, on_delete=models.CASCADE, verbose_name='监控对象')

    name = models.CharField(max_length=100, verbose_name='监控策略名称')
    organizations = models.JSONField(default=list, verbose_name='策略所属组织')

    alert_name = models.CharField(max_length=200, default="", verbose_name='告警名称')

    collect_type = models.CharField(max_length=50, default="", verbose_name='采集类型')

    query_condition = models.JSONField(default=dict, verbose_name='查询条件')

    source = models.JSONField(default=dict, verbose_name="策略适用的资源")

    schedule = models.JSONField(default=dict, verbose_name="策略执行周期, eg: 1h执行一次, 5m执行一次")
    period = models.JSONField(default=dict, verbose_name="每次监控检测的数据周期,eg: 1h内, 5m内")

    algorithm = models.CharField(max_length=50, verbose_name="聚合算法")
    group_by = models.JSONField(default=list, verbose_name="分组字段")
    threshold = models.JSONField(default=list, verbose_name="阈值")
    recovery_condition = models.SmallIntegerField(default=1, verbose_name="多少周期不满足阈值自动恢复")

    no_data_period = models.JSONField(default=dict, verbose_name="无数据告警的数据周期（eg:10m内无数据）")
    no_data_level = models.CharField(max_length=20, default="", verbose_name="无数据告警级别")
    no_data_recovery_period = models.JSONField(default=dict, verbose_name="无数据告警恢复的数据周期（eg:10m内有数据）")

    notice = models.BooleanField(default=True, verbose_name="是否通知")
    notice_type = models.CharField(max_length=50, default="", verbose_name="通知方式")
    notice_type_id = models.IntegerField(default=0, verbose_name="通知方式ID")
    notice_users = models.JSONField(default=list, verbose_name="通知人")

    # 是否启动策略
    enable = models.BooleanField(default=True, verbose_name="是否启用")
    enable_alerts = models.JSONField(default=list, verbose_name="启用的告警类型")
    last_run_time = models.DateTimeField(blank=True, null=True, verbose_name="最后一次执行时间")

    class Meta:
        verbose_name = '监控策略'
        verbose_name_plural = '监控策略'


class PolicyOrganization(TimeInfo, MaintainerInfo):
    policy = models.ForeignKey(MonitorPolicy, on_delete=models.CASCADE, verbose_name='监控策略')
    organization = models.IntegerField(verbose_name='组织id')

    class Meta:
        verbose_name = '监控策略组织'
        verbose_name_plural = '监控策略组织'
        unique_together = ('policy', 'organization')


class MonitorEvent(models.Model):
    LEVEL_CHOICES = [("no_data", "No Data"), ('info', 'Info'), ('warning', 'Warning'), ('error', 'Error'), ('critical', 'Critical')]
    id = models.CharField(primary_key=True, max_length=50, verbose_name='事件ID')
    policy_id = models.IntegerField(db_index=True, verbose_name='监控策略ID')
    monitor_instance_id = models.CharField(db_index=True, max_length=100, verbose_name='监控对象实例ID')
    created_at = models.DateTimeField(db_index=True, auto_now_add=True, verbose_name="事件生成时间" )
    # 事件发生时间
    event_time = models.DateTimeField(blank=True, null=True, verbose_name='事件发生时间')
    value = models.FloatField(blank=True, null=True, verbose_name='事件值')
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, verbose_name='事件级别')
    content = models.TextField(blank=True, verbose_name='事件内容')
    notice_result = models.JSONField(default=list, verbose_name='通知结果')
    class Meta:
        indexes = [models.Index(fields=["policy_id", "monitor_instance_id", "created_at"])]


class MonitorEventRawData(models.Model):
    event = models.ForeignKey(MonitorEvent, on_delete=models.CASCADE, verbose_name='事件')
    data = models.JSONField(default=dict, verbose_name='原始数据')


class MonitorAlertMetricSnapshot(TimeInfo):
    """告警指标快照表 - 记录告警全生命周期内的原始指标数据"""

    alert = models.ForeignKey('MonitorAlert', on_delete=models.CASCADE, verbose_name='关联告警', db_index=True)
    event = models.ForeignKey(MonitorEvent, on_delete=models.CASCADE, verbose_name='关联事件',
                             blank=True, null=True, db_index=True)  # 允许为空，因为正常状态可能没有事件记录
    policy_id = models.IntegerField(db_index=True, verbose_name='监控策略ID')
    monitor_instance_id = models.CharField(db_index=True, max_length=100, verbose_name='监控对象实例ID')

    # 快照数据 - 保持简洁，只存储核心数据
    snapshot_time = models.DateTimeField(db_index=True, verbose_name='快照时间')
    raw_data = models.JSONField(default=list, verbose_name='原始指标数据')

    class Meta:
        verbose_name = '告警指标快照'
        verbose_name_plural = '告警指标快照'
        indexes = [
            models.Index(fields=['alert', 'snapshot_time']),
        ]


class MonitorAlert(TimeInfo):
    STATUS_CHOICES = [('new', 'New'), ('closed', 'Closed'), ('recovered', 'Recovered')]
    ALERT_TYPE_CHOICES = [('alert', 'Alert'), ('no_data', 'No Data')]

    policy_id = models.IntegerField(db_index=True, default=0, verbose_name='监控策略ID')
    monitor_instance_id = models.CharField(db_index=True, default="", max_length=100, verbose_name='监控对象实例ID')
    monitor_instance_name = models.CharField(default="", max_length=100, verbose_name='监控对象实例名称')
    alert_type = models.CharField(db_index=True, default="alert", choices=ALERT_TYPE_CHOICES, max_length=50, verbose_name='告警类型')
    level = models.CharField(db_index=True, default="", max_length=20, verbose_name='最高告警级别')
    value = models.FloatField(blank=True, null=True, verbose_name='最高告警值')
    content = models.TextField(blank=True, verbose_name='告警内容')
    status = models.CharField(db_index=True, max_length=20, default="new", choices=STATUS_CHOICES, verbose_name='告警状态')
    start_event_time = models.DateTimeField(blank=True, null=True, verbose_name='开始事件时间')
    end_event_time = models.DateTimeField(blank=True, null=True, verbose_name='结束事件时间')
    operator = models.CharField(blank=True, null=True, max_length=50, verbose_name='告警处理人')
    info_event_count = models.IntegerField(default=0, verbose_name='信息事件数量')

    class Meta:
        verbose_name = '监控告警'
        verbose_name_plural = '监控告警'
