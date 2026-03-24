# -- coding: utf-8 --
# @File: models.py
# @Time: 2025/5/14 16:14
# @Author: windyzhao
from django.db import models
from django.db.models import JSONField

from apps.alerts.constants.constants import (
    AlertOperate,
    AlertStatus,
    EventAction,
    EventStatus,
    EventType,
    IncidentOperate,
    IncidentStatus,
    LevelType,
    SessionStatus,
)
from apps.alerts.models.alert_source import AlertSource
from apps.core.models.maintainer_info import MaintainerInfo


class Event(models.Model):
    """原始事件"""

    source = models.ForeignKey(AlertSource, on_delete=models.CASCADE, db_index=True, help_text="告警源")
    raw_data = JSONField(help_text="原始数据")
    received_at = models.DateTimeField(auto_now_add=True, db_index=True, help_text="接收时间")

    # 标准化字段
    title = models.CharField(max_length=200, help_text="事件标题")
    description = models.TextField(help_text="事件描述", null=True, blank=True)
    level = models.CharField(max_length=32, db_index=True, help_text="级别")
    # 新版本
    service = models.CharField(max_length=200, help_text="所属服务", null=True, blank=True)
    event_type = models.SmallIntegerField(default=EventType.ALERT, choices=EventType.CHOICES, help_text="发生类型")
    tags = JSONField(default=dict, help_text="事件标签")
    location = models.CharField(max_length=200, help_text="事件发生位置", null=True, blank=True)
    external_id = models.CharField(max_length=128, null=True, blank=True, help_text="外部事件ID")  # 指纹，用于恢复
    # 常规
    start_time = models.DateTimeField(db_index=True, help_text="事件开始时间")
    end_time = models.DateTimeField(null=True, blank=True, db_index=True, help_text="事件结束时间")
    labels = JSONField(default=dict, help_text="事件元数据")
    action = models.CharField(
        max_length=32,
        choices=EventAction.CHOICES,
        default=EventAction.CREATED,
        help_text="事件动作",
    )
    rule_id = models.CharField(max_length=100, null=True, blank=True, help_text="触发该事件的规则ID")
    # f"EVENT-{uuid.uuid4().hex}"
    event_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="事件唯一ID")
    item = models.CharField(max_length=128, null=True, blank=True, db_index=True, help_text="事件指标")
    resource_id = models.CharField(max_length=64, null=True, blank=True, db_index=True, help_text="资源唯一ID")
    resource_type = models.CharField(max_length=64, null=True, blank=True, help_text="资源类型")
    resource_name = models.CharField(max_length=128, null=True, blank=True, help_text="资源名称")
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
            # 注意: JSONField 索引在部分数据库（如达梦）上不支持，通过 migrate_patch 处理
            models.Index(fields=["labels"], name="event_labels_gin"),
        ]
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.title} ({self.level}) at {self.received_at}"


class Alert(models.Model):
    """聚合后的告警"""

    alert_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="告警ID")  # f"ALERT-{uuid.uuid4().hex.upper()}"
    status = models.CharField(
        max_length=32,
        choices=AlertStatus.CHOICES,
        default=AlertStatus.UNASSIGNED,
        help_text="告警状态",
        db_index=True,
    )
    level = models.CharField(max_length=32, db_index=True, help_text="级别")
    events = models.ManyToManyField(Event)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, help_text="创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, help_text="更新时间")

    # 从事件继承的字段
    title = models.CharField(max_length=200, help_text="标题")
    content = models.TextField(help_text="内容")
    labels = JSONField(default=dict, help_text="标签")
    first_event_time = models.DateTimeField(null=True, blank=True, help_text="首次事件时间")
    last_event_time = models.DateTimeField(null=True, blank=True, help_text="最近事件时间")
    item = models.CharField(max_length=128, null=True, blank=True, db_index=True, help_text="事件指标")
    resource_id = models.CharField(max_length=128, null=True, blank=True, db_index=True, help_text="资源唯一ID")
    resource_name = models.CharField(max_length=128, null=True, blank=True, help_text="资源名称")
    resource_type = models.CharField(max_length=64, null=True, blank=True, help_text="资源类型")
    operate = models.CharField(
        max_length=64,
        choices=AlertOperate.CHOICES,
        null=True,
        blank=True,
        help_text="告警操作",
    )
    operator = JSONField(default=list, blank=True, help_text="告警处理人")
    source_name = models.CharField(max_length=100, null=True, blank=True, help_text="告警源名称")
    # 核心指纹字段（用于聚合）
    fingerprint = models.CharField(max_length=32, db_index=True, help_text="告警指纹")  # group_by_field:group_by_value
    group_by_field = models.CharField(max_length=200, null=True, blank=True, help_text="聚合字段")
    rule_id = models.CharField(max_length=256, null=True, blank=True, help_text="触发该事件的规则ID")

    # 会话窗口字段（用于自愈检查）
    is_session_alert = models.BooleanField(default=False, db_index=True, help_text="是否为会话窗口Alert")
    session_status = models.CharField(
        max_length=32,
        choices=SessionStatus.CHOICES,
        null=True,
        blank=True,
        db_index=True,
        help_text="会话Alert状态",
    )
    session_end_time = models.DateTimeField(null=True, blank=True, help_text="会话结束时间")
    team = JSONField(default=list, help_text="关联组织")  # 告警组织

    # 告警通知单独存储

    class Meta:
        db_table = "alerts_alert"
        indexes = [
            # 状态和严重程度组合索引
            models.Index(fields=["status", "level"], name="alert_status_level_idx"),
            # 注意: created_at 已有 db_index=True，无需重复定义
            # 注意: JSONField 索引在部分数据库（如达梦）上不支持，通过 migrate_patch 处理
            models.Index(fields=["operator"], name="alert_operator_gin"),
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
        model_fields = [field.name for field in Alert._meta.get_fields() if not field.is_relation]
        return model_fields


class Incident(MaintainerInfo):
    """聚合后的告警（事件）"""

    incident_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="事故ID")
    status = models.CharField(
        max_length=32,
        choices=IncidentStatus.CHOICES,
        default=IncidentStatus.PENDING,
        help_text="事件状态",
        db_index=True,
    )
    level = models.CharField(max_length=32, db_index=True, help_text="级别")
    alert = models.ManyToManyField(Alert)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, help_text="创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, help_text="更新时间")
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
    fingerprint = models.CharField(max_length=32, null=True, blank=True, db_index=True, help_text="事件指纹")

    class Meta:
        db_table = "alerts_incident"
        indexes = [
            # 注意: created_at 已有 db_index=True，无需重复定义
            # 注意: JSONField 索引在部分数据库（如达梦）上不支持，通过 migrate_patch 处理
            models.Index(fields=["operator"], name="incident_operator_gin"),
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
    description = models.CharField(max_length=300, null=True, blank=True, help_text="级别描述")
    level_type = models.CharField(max_length=32, choices=LevelType.CHOICES, help_text="级别类型")
    built_in = models.BooleanField(default=False, help_text="是否为内置级别")

    class Meta:
        db_table = "alerts_level"
        constraints = [
            models.UniqueConstraint(fields=["level_id", "level_type"], name="unique_level_id_level_type"),
        ]

    def __str__(self):
        return f"{self.level_name}({self.level_id})"
