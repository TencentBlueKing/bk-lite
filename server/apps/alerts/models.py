# -- coding: utf-8 --
# @File: models.py
# @Time: 2025/5/14 16:14
# @Author: windyzhao
from django.db import models
from django.contrib.postgres.indexes import GinIndex, BTreeIndex
from django.db.models import JSONField

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.alerts.constants import (
    AlertsSourceTypes,
    AlertAccessType,
    EventStatus,
    AlertOperate,
    AlertStatus,
    EventAction,
    LevelType,
    AlertAssignmentMatchType,
    AlertShieldMatchType,
    IncidentStatus,
    IncidentOperate,
    NotifyResultStatus,
    LogTargetType,
    LogAction,
    EventType,
    AlarmStrategyType, SessionStatus,
)
from apps.alerts.utils.util import gen_app_secret


# 只查询未被软删除的对象
class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_delete=False)


class AlertSource(MaintainerInfo, TimeInfo):
    """告警源配置"""

    name = models.CharField(max_length=100, help_text="告警源名称")
    source_id = models.CharField(
        max_length=100, unique=True, db_index=True, help_text="告警源ID"
    )
    source_type = models.CharField(
        max_length=20, choices=AlertsSourceTypes.CHOICES, help_text="告警源类型"
    )
    config = JSONField(default=dict, help_text="告警源配置")
    secret = models.CharField("密钥", max_length=100, default=gen_app_secret)
    logo = models.TextField(null=True, blank=True, help_text="告警源logo")  # base64
    access_type = models.CharField(
        max_length=64,
        choices=AlertAccessType.CHOICES,
        default=AlertAccessType.BUILT_IN,
        help_text="告警源接入类型",
    )
    is_active = models.BooleanField(default=True, db_index=True, help_text="是否启用")
    is_effective = models.BooleanField(
        default=True, db_index=False, help_text="是否生效"
    )
    description = models.TextField(null=True, blank=True, help_text="告警源描述")
    last_active_time = models.DateTimeField(
        null=True, blank=True, help_text="最近活跃时间"
    )
    is_delete = models.BooleanField(default=False, db_index=True, help_text="是否删除")

    class Meta:
        indexes = [
            models.Index(fields=["name", "source_type"]),
        ]

    all_objects = models.Manager()  # 所有对象，包括被软删除的对象
    objects = SoftDeleteManager()  # 只查询未被软删除的对象

    def __str__(self):
        return f"{self.name} ({self.source_type})"


class Event(models.Model):
    """原始事件"""

    source = models.ForeignKey(
        AlertSource, on_delete=models.CASCADE, db_index=True, help_text="告警源"
    )
    raw_data = JSONField(help_text="原始数据")
    received_at = models.DateTimeField(
        auto_now_add=True, db_index=True, help_text="接收时间"
    )

    # 标准化字段
    title = models.CharField(max_length=200, help_text="事件标题")
    description = models.TextField(help_text="事件描述", null=True, blank=True)
    level = models.CharField(max_length=32, db_index=True, help_text="级别")
    # 新版本
    service = models.CharField(
        max_length=200, help_text="所属服务", null=True, blank=True
    )
    event_type = models.SmallIntegerField(
        default=EventType.ALERT, choices=EventType.CHOICES, help_text="发生类型"
    )
    tags = JSONField(default=dict, help_text="事件标签")
    location = models.CharField(
        max_length=200, help_text="事件发生位置", null=True, blank=True
    )
    external_id = models.CharField(
        max_length=128, null=True, blank=True, help_text="外部事件ID"
    )  # 指纹，用于恢复
    # 常规
    start_time = models.DateTimeField(db_index=True, help_text="事件开始时间")
    end_time = models.DateTimeField(
        null=True, blank=True, db_index=True, help_text="事件结束时间"
    )
    labels = JSONField(default=dict, help_text="事件元数据")
    action = models.CharField(
        max_length=32,
        choices=EventAction.CHOICES,
        default=EventAction.CREATED,
        help_text="事件动作",
    )
    rule_id = models.CharField(
        max_length=100, null=True, blank=True, help_text="触发该事件的规则ID"
    )
    # f"EVENT-{uuid.uuid4().hex}"
    event_id = models.CharField(
        max_length=100, unique=True, db_index=True, help_text="事件唯一ID"
    )
    item = models.CharField(
        max_length=128, null=True, blank=True, db_index=True, help_text="事件指标"
    )
    resource_id = models.CharField(
        max_length=64, null=True, blank=True, db_index=True, help_text="资源唯一ID"
    )
    resource_type = models.CharField(
        max_length=64, null=True, blank=True, help_text="资源类型"
    )
    resource_name = models.CharField(
        max_length=128, null=True, blank=True, help_text="资源名称"
    )
    status = models.CharField(
        max_length=32,
        choices=EventStatus.CHOICES,
        default=EventStatus.RECEIVED,
        help_text="事件状态",
    )
    assignee = JSONField(default=list, blank=True, help_text="事件责任人")
    # note = models.TextField(null=True, blank=True, help_text="事件备注")
    value = models.FloatField(blank=True, null=True, verbose_name="事件值")

    class Meta:
        db_table = "alerts_event"
        indexes = [
            models.Index(fields=["source", "received_at"]),
            GinIndex(fields=["labels"], name="event_labels_gin"),
        ]
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.title} ({self.level}) at {self.received_at}"


class Alert(models.Model):
    """聚合后的告警"""

    alert_id = models.CharField(
        max_length=100, unique=True, db_index=True, help_text="告警ID"
    )  # f"ALERT-{uuid.uuid4().hex.upper()}"
    status = models.CharField(
        max_length=32,
        choices=AlertStatus.CHOICES,
        default=AlertStatus.UNASSIGNED,
        help_text="告警状态",
        db_index=True,
    )
    level = models.CharField(max_length=32, db_index=True, help_text="级别")
    events = models.ManyToManyField(Event)
    created_at = models.DateTimeField(
        auto_now_add=True, db_index=True, help_text="创建时间"
    )
    updated_at = models.DateTimeField(
        auto_now=True, db_index=True, help_text="更新时间"
    )

    # 从事件继承的字段
    title = models.CharField(max_length=200, help_text="标题")
    content = models.TextField(help_text="内容")
    labels = JSONField(default=dict, help_text="标签")
    first_event_time = models.DateTimeField(
        null=True, blank=True, help_text="首次事件时间"
    )
    last_event_time = models.DateTimeField(
        null=True, blank=True, help_text="最近事件时间"
    )
    item = models.CharField(
        max_length=128, null=True, blank=True, db_index=True, help_text="事件指标"
    )
    resource_id = models.CharField(
        max_length=128, null=True, blank=True, db_index=True, help_text="资源唯一ID"
    )
    resource_name = models.CharField(
        max_length=128, null=True, blank=True, help_text="资源名称"
    )
    resource_type = models.CharField(
        max_length=64, null=True, blank=True, help_text="资源类型"
    )
    operate = models.CharField(
        max_length=64,
        choices=AlertOperate.CHOICES,
        null=True,
        blank=True,
        help_text="告警操作",
    )
    operator = JSONField(default=list, blank=True, help_text="告警处理人")
    source_name = models.CharField(
        max_length=100, null=True, blank=True, help_text="告警源名称"
    )
    # 核心指纹字段（用于聚合）
    fingerprint = models.CharField(
        max_length=32, db_index=True, help_text="告警指纹"
    )  # group_by_field:group_by_value
    group_by_field = models.CharField(
        max_length=200, null=True, blank=True, help_text="聚合字段"
    )
    rule_id = models.CharField(
        max_length=256, null=True, blank=True, help_text="触发该事件的规则ID"
    )

    # 会话窗口字段（用于自愈检查）
    is_session_alert = models.BooleanField(
        default=False, db_index=True, help_text="是否为会话窗口Alert"
    )
    session_status = models.CharField(
        max_length=32,
        choices=SessionStatus.CHOICES,
        null=True,
        blank=True,
        db_index=True,
        help_text="会话Alert状态",
    )
    session_end_time = models.DateTimeField(
        null=True, blank=True, help_text="会话结束时间"
    )
    team = JSONField(default=list, help_text="关联组织")  # 告警组织

    # 告警通知单独存储

    class Meta:
        db_table = "alerts_alert"
        indexes = [
            # 状态和严重程度组合索引
            models.Index(fields=["status", "level"], name="alert_status_level_idx"),
            # 时间范围查询优化
            BTreeIndex(fields=["created_at"], name="alert_created_btree"),
            # JSONB字段索引
            GinIndex(fields=["operator"], name="alert_operator_gin"),
        ]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.alert_id} - {self.title} ({self.status})"

    @property
    def format_created_at(self):
        """格式化创建时间"""
        return self.created_at.strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def model_fields(cls):
        model_fields = [
            field.name for field in Alert._meta.get_fields() if not field.is_relation
        ]
        return model_fields


class Incident(MaintainerInfo):
    """聚合后的告警（事件）"""

    incident_id = models.CharField(
        max_length=100, unique=True, db_index=True, help_text="事故ID"
    )
    status = models.CharField(
        max_length=32,
        choices=IncidentStatus.CHOICES,
        default=IncidentStatus.PENDING,
        help_text="事件状态",
        db_index=True,
    )
    level = models.CharField(max_length=32, db_index=True, help_text="级别")
    alert = models.ManyToManyField(Alert)
    created_at = models.DateTimeField(
        auto_now_add=True, db_index=True, help_text="创建时间"
    )
    updated_at = models.DateTimeField(
        auto_now=True, db_index=True, help_text="更新时间"
    )
    title = models.CharField(max_length=256, help_text="标题")
    content = models.TextField(null=True, blank=True, help_text="内容")
    note = models.TextField(null=True, blank=True, help_text="事件备注")
    labels = JSONField(default=dict, help_text="标签")
    operate = models.CharField(
        max_length=64,
        choices=IncidentOperate.CHOICES,
        null=True,
        blank=True,
        help_text="操作",
    )
    operator = JSONField(default=list, blank=True, help_text="处理人")
    # 核心指纹字段（用于聚合）
    fingerprint = models.CharField(
        max_length=32, null=True, blank=True, db_index=True, help_text="事件指纹"
    )

    class Meta:
        db_table = "alerts_incident"
        indexes = [
            # 时间范围查询优化
            BTreeIndex(fields=["created_at"], name="incident_created_btree"),
            # JSONB字段索引
            GinIndex(fields=["operator"], name="incident_operator_gin"),
        ]

    def __str__(self):
        return f"{self.incident_id} - {self.title} ({self.status})"

    @property
    def format_created_at(self):
        """格式化创建时间"""
        return self.created_at.strftime("%Y-%m-%d %H:%M:%S")


class Level(models.Model):
    """事件级别配置"""

    level_id = models.SmallIntegerField(help_text="级别ID")
    level_name = models.CharField(max_length=32, help_text="级别名称")
    level_display_name = models.CharField(max_length=32, help_text="级别中文名称")
    color = models.CharField(max_length=16, null=True, blank=True, help_text="颜色代码")
    icon = models.TextField(null=True, blank=True, help_text="图标base64")
    description = models.CharField(
        max_length=300, null=True, blank=True, help_text="级别描述"
    )
    level_type = models.CharField(
        max_length=32, choices=LevelType.CHOICES, help_text="级别类型"
    )
    built_in = models.BooleanField(default=False, help_text="是否为内置级别")

    class Meta:
        db_table = "alerts_level"
        constraints = [
            models.UniqueConstraint(
                fields=["level_id", "level_type"], name="unique_level_id_level_type"
            ),
        ]

    def __str__(self):
        return f"{self.level_name}({self.level_id})"


class AlertAssignment(MaintainerInfo, TimeInfo):
    """
    分派策略
    """

    name = models.CharField(max_length=200, unique=True, help_text="分派策略名称")
    match_type = models.CharField(
        max_length=32, choices=AlertAssignmentMatchType.CHOICES, help_text="匹配类型"
    )
    match_rules = JSONField(default=list, help_text="匹配规则")
    personnel = models.JSONField(
        default=list, blank=True, null=True, help_text="分派人员"
    )
    notify_channels = JSONField(default=list, help_text="通知渠道")
    notification_scenario = JSONField(default=list, help_text="通知场景")
    config = JSONField(default=dict, help_text="分派配置")
    notification_frequency = models.JSONField(
        default=dict, blank=True, null=True, help_text="通知频率配置"
    )
    is_active = models.BooleanField(default=True, db_index=True, help_text="是否启用")

    class Meta:
        db_table = "alerts_alert_assignment"

    def __str__(self):
        return self.name


class AlertShield(MaintainerInfo, TimeInfo):
    """
    告警屏蔽策略
    """

    name = models.CharField(max_length=200, unique=True, help_text="屏蔽策略名称")
    match_type = models.CharField(
        max_length=32, choices=AlertShieldMatchType.CHOICES, help_text="匹配类型"
    )
    match_rules = JSONField(default=list, help_text="匹配规则")
    suppression_time = models.JSONField(default=dict, help_text="屏蔽时间配置")
    is_active = models.BooleanField(default=True, db_index=True, help_text="是否启用")

    class Meta:
        db_table = "alerts_alert_shield"

    def __str__(self):
        return self.name


class AlertReminderTask(models.Model):
    """
    告警提醒任务 - 轮询版本
    """

    alert = models.OneToOneField(
        Alert, on_delete=models.CASCADE, help_text="关联的告警", primary_key=True
    )
    assignment = models.ForeignKey(
        AlertAssignment, on_delete=models.CASCADE, help_text="分派策略"
    )

    # 提醒状态
    is_active = models.BooleanField(default=True, help_text="是否激活")
    reminder_count = models.IntegerField(default=0, help_text="已提醒次数")

    # 当前配置（冗余存储，避免策略变更影响）
    current_frequency_minutes = models.IntegerField(help_text="当前提醒频率(分钟)")
    current_max_reminders = models.IntegerField(help_text="当前最大提醒次数")

    # 时间记录
    next_reminder_time = models.DateTimeField(help_text="下次提醒时间")
    last_reminder_time = models.DateTimeField(
        null=True, blank=True, help_text="上次提醒时间"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "alerts_reminder_task"
        indexes = [
            models.Index(fields=["is_active", "next_reminder_time"]),
        ]

    def __str__(self):
        return f"ReminderTask for Alert {self.alert.alert_id}"


class AlarmStrategy(MaintainerInfo, TimeInfo):
    """告警策略模型"""

    name = models.CharField(max_length=100, help_text="策略名称")
    strategy_type = models.CharField(
        max_length=32,
        choices=AlarmStrategyType.CHOICES,
        default=AlarmStrategyType.SMART_DENOISE,
        help_text="策略类型",
    )
    is_active = models.BooleanField(default=True, help_text="是否启用")
    description = models.TextField(null=True, blank=True, help_text="策略描述")
    team = JSONField(default=list, help_text="关联组织")  # 策略组织
    dispatch_team = JSONField(
        default=list, help_text="分派组织"
    )  # Event聚合Alert后的组织
    # {"match_rules":{"type":"ALL","value":[{}]}}
    match_rules = JSONField(default=list, help_text="匹配规则")
    params = JSONField(
        default=dict, help_text="策略参数"
    )  # {"type":[],"window_size":10}
    auto_close = models.BooleanField(default=True, help_text="是否自动关闭告警")
    close_minutes = models.IntegerField(default=120, help_text="自动关闭时间(分钟)")

    class Meta:
        db_table = "alerts_alarm_strategy"
        verbose_name = "告警策略"
        verbose_name_plural = "告警策略"
        unique_together = ("name", "strategy_type")


# 通知结果存储
class NotifyResult(models.Model):
    """通知结果"""

    notify_people = JSONField(default=list, help_text="通知人员")
    notify_channel = models.CharField(
        max_length=100, null=True, blank=True, help_text="通知渠道"
    )
    notify_channel_name = models.CharField(
        max_length=100, null=True, blank=True, help_text="通知渠道名称"
    )
    notify_time = models.DateTimeField(auto_now_add=True, help_text="通知时间")
    notify_result = models.CharField(
        max_length=30, choices=NotifyResultStatus.CHOICES, help_text="通知结果"
    )
    notify_object = models.CharField(
        max_length=100, null=True, blank=True, help_text="通知对象ID"
    )
    notify_type = models.CharField(
        max_length=50, null=True, blank=True, help_text="通知类型"
    )

    class Meta:
        db_table = "alerts_notify_result"
        verbose_name = "通知结果"
        verbose_name_plural = "通知结果"

    def __str__(self):
        return f"NotifyResult for {self.notify_object} at {self.notify_time} - {self.notify_result}"


class SystemSetting(TimeInfo):
    """系统设置模型"""

    key = models.CharField(max_length=100, unique=True, help_text="设置键")
    value = JSONField(help_text="设置值", default=dict)
    description = models.TextField(null=True, blank=True, help_text="设置描述")
    is_activate = models.BooleanField(
        default=False, db_index=True, help_text="是否启用"
    )
    is_build = models.BooleanField(
        default=True, db_index=True, help_text="是否为内置设置"
    )

    class Meta:
        db_table = "alerts_system_setting"
        verbose_name = "系统设置"
        verbose_name_plural = "系统设置"

    def __str__(self):
        return self.key


class OperatorLog(models.Model):
    """操作日志模型"""

    operator = models.CharField(max_length=64, default="admin", help_text="操作人")
    action = models.CharField(
        max_length=32, choices=LogAction.CHOICES, help_text="操作类型"
    )
    target_type = models.CharField(
        max_length=32,
        choices=LogTargetType.CHOICES,
        default=LogTargetType.SYSTEM,
        help_text="目标类型",
    )
    operator_object = models.CharField(
        max_length=100, null=True, blank=True, help_text="操作对象"
    )
    target_id = models.CharField(
        max_length=100, null=True, blank=True, help_text="目标ID"
    )
    overview = models.TextField(null=True, blank=True, help_text="操作概述")
    created_at = models.DateTimeField(
        help_text="Created Time", auto_now_add=True, db_index=True
    )

    class Meta:
        db_table = "alerts_operator_log"
        verbose_name = "操作日志"
        verbose_name_plural = "操作日志"

    def __str__(self):
        return (
            f"{self.operator} - {self.action} on {self.target_type}({self.target_id})"
        )
