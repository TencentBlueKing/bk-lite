from django.db import models
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.log.models import CollectType
from apps.core.fields import S3JSONField


class Policy(TimeInfo, MaintainerInfo):

    # 基本信息
    name = models.CharField(max_length=255, verbose_name="策略名称")
    collect_type = models.ForeignKey(CollectType, on_delete=models.CASCADE, verbose_name="采集方式")
    last_run_time = models.DateTimeField(blank=True, null=True, verbose_name="最后一次执行时间")

    # 日志分组配置 - 策略作用范围
    log_groups = models.JSONField(default=list, verbose_name="日志分组范围", help_text="策略监控的日志分组ID列表")

    # 告警条件（关键字 & 聚合都可能用到）
    alert_type = models.CharField(max_length=50, verbose_name="告警类型")
    alert_name = models.CharField(max_length=255, verbose_name="告警名称")
    alert_level = models.CharField(max_length=30, verbose_name="告警等级")
    alert_condition = models.JSONField(default=dict, verbose_name="告警条件")
    schedule = models.JSONField(default=dict, verbose_name="策略执行周期, eg: 1h执行一次, 5m执行一次")
    period = models.JSONField(default=dict, verbose_name="每次监控检测的数据周期,eg: 1h内, 5m内")
    show_fields = models.JSONField(default=list, verbose_name="展示字段")

    # 通知配置
    notice = models.BooleanField(default=True, verbose_name="是否通知")
    notice_type = models.CharField(max_length=50, default="", verbose_name="通知方式")
    notice_type_id = models.IntegerField(default=0, verbose_name="通知方式ID")
    notice_users = models.JSONField(default=list, verbose_name="通知人")

    enable = models.BooleanField(default=True, verbose_name="是否启用")

    class Meta:
        verbose_name = "告警策略"
        verbose_name_plural = "告警策略"
        unique_together = ('name', 'collect_type')


class PolicyOrganization(TimeInfo, MaintainerInfo):
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, verbose_name='监控策略')
    organization = models.IntegerField(verbose_name='组织id')

    class Meta:
        verbose_name = '策略组织'
        verbose_name_plural = '策略组织'
        unique_together = ('policy', 'organization')


class Alert(TimeInfo):
    """
    告警记录
    """
    id = models.CharField(primary_key=True, max_length=50, verbose_name="告警ID")
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, verbose_name="关联策略")
    source_id = models.CharField(max_length=100, db_index=True, verbose_name='资源ID')
    collect_type = models.ForeignKey(CollectType, on_delete=models.CASCADE, verbose_name="采集方式")
    level = models.CharField(db_index=True, default="", max_length=20, verbose_name='最高告警级别')
    value = models.FloatField(blank=True, null=True, verbose_name='最高告警值')
    content = models.TextField(blank=True, verbose_name='告警内容')
    status = models.CharField(db_index=True, max_length=20, default="new", verbose_name='告警状态')
    start_event_time = models.DateTimeField(blank=True, null=True, verbose_name='开始事件时间')
    end_event_time = models.DateTimeField(blank=True, null=True, verbose_name='结束事件时间')
    operator = models.CharField(blank=True, null=True, max_length=50, verbose_name='告警处理人')
    info_event_count = models.IntegerField(default=0, verbose_name='正常事件计数')
    notice = models.BooleanField(default=False, verbose_name="是否已通知")
    class Meta:
        verbose_name = "告警记录"
        verbose_name_plural = "告警记录"


class Event(TimeInfo):
    """
    事件记录
    """
    id = models.CharField(primary_key=True, max_length=50, verbose_name="事件ID")
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, verbose_name="关联策略")
    source_id = models.CharField(max_length=100, db_index=True, verbose_name='资源ID')
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, verbose_name="关联告警")
    event_time = models.DateTimeField(blank=True, null=True, verbose_name='事件发生时间')
    value = models.FloatField(blank=True, null=True, verbose_name='事件值')
    level = models.CharField(max_length=20, verbose_name='事件级别')
    content = models.TextField(blank=True, verbose_name='事件内容')
    notice_result = models.JSONField(default=list, verbose_name='通知结果')

    class Meta:
        verbose_name = "事件记录"
        verbose_name_plural = "事件记录"


class EventRawData(models.Model):
    """
    事件原始数据
    使用 S3JSONField 自动存储到 MinIO，支持自动压缩
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, verbose_name='事件')
    data = S3JSONField(
        bucket_name='log-alert-raw-data',
        compressed=True,
        verbose_name='原始数据',
        help_text='自动压缩并存储到 MinIO/S3'
    )

    class Meta:
        verbose_name = "事件原始数据"
        verbose_name_plural = "事件原始数据"
