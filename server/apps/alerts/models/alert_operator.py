# -- coding: utf-8 --
# @File: alert_operator.py
# @Time: 2026/2/5 16:19
# @Author: windyzhao
from django.db import models
from django.db.models import JSONField

from apps.alerts.constants.constants import AlarmStrategyType, AlertShieldMatchType, AlertAssignmentMatchType, NotifyResultStatus
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


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
        "Alert", on_delete=models.CASCADE, help_text="关联的告警", primary_key=True
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


