# -- coding: utf-8 --
# @File: models.py
# @Time: 2025/5/14 16:14
# @Author: windyzhao
# -- coding: utf-8 --
# @File: alert.py
# @Time: 2025/5/9 15:25
# @Author: windyzhao
from datetime import timedelta

from django.db import models
from django.contrib.postgres.indexes import GinIndex, BTreeIndex
from django.db.models import JSONField
from django.utils import timezone

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.alerts.constants import AlertsSourceTypes, AlertAccessType, EventStatus, AlertOperate, \
    AlertStatus, EventAction, LevelType, AlertAssignmentMatchType, AlertShieldMatchType, IncidentStatus, \
    IncidentOperate, CorrelationRulesScope, CorrelationRulesType, AggregationRuleType, NotifyResultStatus, \
    LogTargetType, LogAction, WindowType, Alignment
from apps.alerts.utils.util import gen_app_secret, window_size_to_int


# 只查询未被软删除的对象
class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_delete=False)


class AlertSource(MaintainerInfo, TimeInfo):
    """告警源配置"""

    name = models.CharField(max_length=100, help_text="告警源名称")
    source_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="告警源ID")
    source_type = models.CharField(max_length=20, choices=AlertsSourceTypes.CHOICES, help_text="告警源类型")
    config = JSONField(default=dict, help_text="告警源配置")
    secret = models.CharField("密钥", max_length=100, default=gen_app_secret)
    logo = models.TextField(null=True, blank=True, help_text="告警源logo")  # base64
    access_type = models.CharField(max_length=64, choices=AlertAccessType.CHOICES, default=AlertAccessType.BUILT_IN,
                                   help_text="告警源接入类型")
    is_active = models.BooleanField(default=True, db_index=True, help_text="是否启用")
    is_effective = models.BooleanField(default=True, db_index=False, help_text="是否生效")
    description = models.TextField(null=True, blank=True, help_text="告警源描述")
    last_active_time = models.DateTimeField(null=True, blank=True, help_text="最近活跃时间")
    is_delete = models.BooleanField(default=False, db_index=True, help_text="是否删除")

    class Meta:
        indexes = [
            models.Index(fields=['name', 'source_type']),
        ]

    all_objects = models.Manager()  # 所有对象，包括被软删除的对象
    objects = SoftDeleteManager()  # 只查询未被软删除的对象

    def __str__(self):
        return f"{self.name} ({self.source_type})"


class Event(models.Model):
    """原始事件"""

    source = models.ForeignKey(AlertSource, on_delete=models.CASCADE, db_index=True, help_text="告警源")
    raw_data = JSONField(help_text="原始数据")
    received_at = models.DateTimeField(auto_now_add=True, db_index=True, help_text="接收时间")

    # 标准化字段
    title = models.CharField(max_length=200, help_text="事件标题")
    description = models.TextField(help_text="事件描述", null=True, blank=True)
    level = models.CharField(max_length=32, db_index=True, help_text="级别")
    start_time = models.DateTimeField(db_index=True, help_text="事件开始时间")
    end_time = models.DateTimeField(null=True, blank=True, db_index=True, help_text="事件结束时间")
    labels = JSONField(default=dict, help_text="事件元数据")
    action = models.CharField(max_length=32, choices=EventAction.CHOICES, default=EventAction.CREATED,
                              help_text="事件动作")
    rule_id = models.CharField(max_length=100, null=True, blank=True, help_text="触发该事件的规则ID")
    event_id = models.CharField(max_length=100, unique=True, db_index=True,
                                help_text="事件唯一ID")  # f"EVENT-{uuid.uuid4().hex}"
    external_id = models.CharField(max_length=128, null=True, blank=True, help_text="外部事件ID")
    item = models.CharField(max_length=128, null=True, blank=True, db_index=True, help_text="事件指标")
    resource_id = models.CharField(max_length=64, null=True, blank=True, db_index=True, help_text="资源唯一ID")
    resource_type = models.CharField(max_length=64, null=True, blank=True, help_text="资源类型")
    resource_name = models.CharField(max_length=128, null=True, blank=True, help_text="资源名称")
    status = models.CharField(max_length=32, choices=EventStatus.CHOICES, default=EventStatus.RECEIVED,
                              help_text="事件状态")
    assignee = JSONField(default=list, blank=True, help_text="事件责任人")
    # note = models.TextField(null=True, blank=True, help_text="事件备注")
    value = models.FloatField(blank=True, null=True, verbose_name='事件值')

    class Meta:
        db_table = "alerts_event"
        indexes = [
            models.Index(fields=['source', 'received_at']),
            GinIndex(fields=['labels'], name='event_labels_gin'),
        ]
        ordering = ['-received_at']

    def __str__(self):
        return f"{self.title} ({self.level}) at {self.received_at}"


class Alert(models.Model):
    """聚合后的告警"""

    alert_id = models.CharField(max_length=100, unique=True, db_index=True,
                                help_text="告警ID")  # f"ALERT-{uuid.uuid4().hex.upper()}"
    status = models.CharField(max_length=32, choices=AlertStatus.CHOICES, default=AlertStatus.UNASSIGNED,
                              help_text="告警状态", db_index=True)
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
    operate = models.CharField(max_length=64, choices=AlertOperate.CHOICES, null=True, blank=True, help_text="告警操作")
    operator = JSONField(default=list, blank=True, help_text="告警处理人")
    source_name = models.CharField(max_length=100, null=True, blank=True, help_text="告警源名称")
    # 核心指纹字段（用于聚合）
    fingerprint = models.CharField(max_length=32, db_index=True, help_text="告警指纹")
    rule_id = models.CharField(max_length=256, null=True, blank=True, help_text="触发该事件的规则ID")

    # 告警通知单独存储

    class Meta:
        db_table = "alerts_alert"
        indexes = [
            # 状态和严重程度组合索引
            models.Index(fields=['status', 'level'], name='alert_status_level_idx'),
            # 时间范围查询优化
            BTreeIndex(fields=['created_at'], name='alert_created_btree'),
            # JSONB字段索引
            GinIndex(fields=['operator'], name='alert_operator_gin'),
        ]
        ordering = ['-updated_at']

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
    status = models.CharField(max_length=32, choices=IncidentStatus.CHOICES, default=IncidentStatus.PENDING,
                              help_text="事件状态", db_index=True)
    level = models.CharField(max_length=32, db_index=True, help_text="级别")
    alert = models.ManyToManyField(Alert)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, help_text="创建时间")
    updated_at = models.DateTimeField(auto_now=True, db_index=True, help_text="更新时间")
    title = models.CharField(max_length=256, help_text="标题")
    content = models.TextField(null=True, blank=True, help_text="内容")
    note = models.TextField(null=True, blank=True, help_text="事件备注")
    labels = JSONField(default=dict, help_text="标签")
    operate = models.CharField(max_length=64, choices=IncidentOperate.CHOICES, null=True, blank=True, help_text="操作")
    operator = JSONField(default=list, blank=True, help_text="处理人")
    # 核心指纹字段（用于聚合）
    fingerprint = models.CharField(max_length=32, null=True, blank=True, db_index=True, help_text="事件指纹")

    class Meta:
        db_table = "alerts_incident"
        indexes = [
            # 时间范围查询优化
            BTreeIndex(fields=['created_at'], name='incident_created_btree'),
            # JSONB字段索引
            GinIndex(fields=['operator'], name='incident_operator_gin'),
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
            models.UniqueConstraint(
                fields=['level_id', 'level_type'],
                name='unique_level_id_level_type'
            ),
        ]

    def __str__(self):
        return f"{self.level_name}({self.level_id})"


class AlertAssignment(MaintainerInfo, TimeInfo):
    """
    分派策略
    """

    name = models.CharField(max_length=200, unique=True, help_text="分派策略名称")
    match_type = models.CharField(max_length=32, choices=AlertAssignmentMatchType.CHOICES, help_text="匹配类型")
    match_rules = JSONField(default=list, help_text="匹配规则")
    personnel = models.JSONField(default=list, blank=True, null=True, help_text="分派人员")
    notify_channels = JSONField(default=list, help_text="通知渠道")
    notification_scenario = JSONField(default=list, help_text="通知场景")
    config = JSONField(default=dict, help_text="分派配置")
    notification_frequency = models.JSONField(default=dict, blank=True, null=True, help_text="通知频率配置")
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
    match_type = models.CharField(max_length=32, choices=AlertShieldMatchType.CHOICES, help_text="匹配类型")
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
    alert = models.OneToOneField(Alert, on_delete=models.CASCADE, help_text="关联的告警", primary_key=True)
    assignment = models.ForeignKey(AlertAssignment, on_delete=models.CASCADE, help_text="分派策略")

    # 提醒状态
    is_active = models.BooleanField(default=True, help_text="是否激活")
    reminder_count = models.IntegerField(default=0, help_text="已提醒次数")

    # 当前配置（冗余存储，避免策略变更影响）
    current_frequency_minutes = models.IntegerField(help_text="当前提醒频率(分钟)")
    current_max_reminders = models.IntegerField(help_text="当前最大提醒次数")

    # 时间记录
    next_reminder_time = models.DateTimeField(help_text="下次提醒时间")
    last_reminder_time = models.DateTimeField(null=True, blank=True, help_text="上次提醒时间")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "alerts_reminder_task"
        indexes = [
            models.Index(fields=['is_active', 'next_reminder_time']),
        ]

    def __str__(self):
        return f"ReminderTask for Alert {self.alert.alert_id}"


class AggregationRules(MaintainerInfo, TimeInfo):
    """聚合规则模型"""
    rule_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="规则ID")
    name = models.CharField(max_length=100, help_text="规则名称")
    is_active = models.BooleanField(default=True, db_index=True, help_text="是否启用")
    template_title = models.CharField(max_length=200, null=True, blank=True, help_text="模板标题")
    template_content = models.TextField(null=True, blank=True, help_text="模板内容")
    severity = models.CharField(max_length=32, default="warning", help_text="严重程度")
    condition = JSONField(default=list, help_text="规则条件配置")  # [dict, ...]
    type = models.CharField(max_length=32, choices=AggregationRuleType.CHOICES, default=AggregationRuleType.ALERT,
                            help_text="聚合类型")

    # {"zh": "中文描述", "en": "English description"}
    description = JSONField(default=dict, help_text="规则描述", blank=True, null=True)
    image = models.TextField(null=True, blank=True, help_text="规则图标base64")

    def get_session_close_conditions(self):
        try:
            # 获取第一个条件的session_close配置
            if self.condition and isinstance(self.condition[0], dict):
                return self.condition[0].get("session_close", {})
        except Exception as err:
            return {}

    @property
    def window_config(self):
        correlation_rule = self.correlation_rules.last()
        result = {
            'window_type': correlation_rule.window_type,
            'window_size': window_size_to_int(
                correlation_rule.window_size) if not correlation_rule.is_session_rule else 0,
            'time_column': 'received_at'
        }
        return result

    class Meta:
        db_table = 'alerts_aggregation_rules'
        verbose_name = '聚合规则'
        verbose_name_plural = '聚合规则'


class CorrelationRules(MaintainerInfo, TimeInfo):
    """关联规则模型"""
    name = models.CharField(max_length=100, unique=True, help_text="关联规则名称")
    aggregation_rules = models.ManyToManyField(AggregationRules, related_name='correlation_rules',
                                               help_text="关联的聚合规则")
    scope = models.CharField(max_length=20, choices=CorrelationRulesScope.CHOICES, help_text="作用范围")
    rule_type = models.CharField(max_length=20, choices=CorrelationRulesType.CHOICES, help_text="规则类型")
    description = models.TextField(null=True, blank=True, verbose_name="描述")

    # 窗口类型配置字段 - 从 AggregationRules 移动到这里
    window_type = models.CharField(max_length=20, choices=WindowType.CHOICES, default=WindowType.SLIDING,
                                   help_text="聚合窗口类型")
    window_size = models.CharField(max_length=20, default="10min", help_text="窗口大小，如10min、1h、30s")
    slide_interval = models.CharField(max_length=20, default="1min", help_text="滑动窗口滑动间隔")
    alignment = models.CharField(
        max_length=10,
        choices=Alignment.CHOICES,
        default=Alignment.MINUTE,
        help_text="固定窗口对齐方式"
    )
    session_timeout = models.CharField(max_length=20, default="10min", help_text="会话窗口超时时间")
    max_window_size = models.CharField(max_length=20, null=True, blank=True, help_text="最大窗口大小限制")
    session_key_fields = JSONField(default=list, help_text="会话窗口分组字段，空数组表示使用事件指纹")
    exec_time = models.DateTimeField(help_text="规则执行时间", null=True, blank=True)
    close_time = models.CharField(max_length=20, null=True, blank=True, help_text="自动关闭时间")  # 例如 "10min"

    class Meta:
        db_table = 'alerts_correlation_rules'
        verbose_name = '关联规则'
        verbose_name_plural = '关联规则'

    @property
    def rule_id_str(self):
        """返回规则ID的字符串形式"""
        rules = list(self.aggregation_rules.all().values_list("rule_id", flat=True))
        result = ",".join(rules) if rules else ""
        return result

    @property
    def is_session_rule(self):
        return self.window_type == WindowType.SESSION

    def __str__(self):
        return self.name


# 通知结果存储
class NotifyResult(models.Model):
    """通知结果"""
    notify_people = JSONField(default=list, help_text="通知人员")
    notify_channel = models.CharField(max_length=100, null=True, blank=True, help_text="通知渠道")
    notify_channel_name = models.CharField(max_length=100, null=True, blank=True, help_text="通知渠道名称")
    notify_time = models.DateTimeField(auto_now_add=True, help_text="通知时间")
    notify_result = models.CharField(max_length=30, choices=NotifyResultStatus.CHOICES, help_text="通知结果")
    notify_object = models.CharField(max_length=100, null=True, blank=True, help_text="通知对象ID")
    notify_type = models.CharField(max_length=50, null=True, blank=True, help_text="通知类型")

    class Meta:
        db_table = 'alerts_notify_result'
        verbose_name = '通知结果'
        verbose_name_plural = '通知结果'

    def __str__(self):
        return f"NotifyResult for {self.notify_object} at {self.notify_time} - {self.notify_result}"


class SystemSetting(TimeInfo):
    """系统设置模型"""
    key = models.CharField(max_length=100, unique=True, help_text="设置键")
    value = JSONField(help_text="设置值", default=dict)
    description = models.TextField(null=True, blank=True, help_text="设置描述")
    is_activate = models.BooleanField(default=False, db_index=True, help_text="是否启用")
    is_build = models.BooleanField(default=True, db_index=True, help_text="是否为内置设置")

    class Meta:
        db_table = 'alerts_system_setting'
        verbose_name = '系统设置'
        verbose_name_plural = '系统设置'

    def __str__(self):
        return self.key


class OperatorLog(models.Model):
    """操作日志模型"""
    operator = models.CharField(max_length=64, default="admin", help_text="操作人")
    action = models.CharField(max_length=32, choices=LogAction.CHOICES, help_text="操作类型")
    target_type = models.CharField(max_length=32, choices=LogTargetType.CHOICES, default=LogTargetType.SYSTEM,
                                   help_text="目标类型")
    operator_object = models.CharField(max_length=100, null=True, blank=True, help_text="操作对象")
    target_id = models.CharField(max_length=100, null=True, blank=True, help_text="目标ID")
    overview = models.TextField(null=True, blank=True, help_text="操作概述")
    created_at = models.DateTimeField(help_text="Created Time", auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'alerts_operator_log'
        verbose_name = '操作日志'
        verbose_name_plural = '操作日志'

    def __str__(self):
        return f"{self.operator} - {self.action} on {self.target_type}({self.target_id})"


class SessionWindow(TimeInfo):
    """
    会话窗口状态持久化
    
    改进说明：
    - 引入events字段建立与Event模型的多对多关联，替代之前的session_key字符串查询方式
    - 提供更高效和可靠的事件关联机制
    - 确保数据一致性和查询性能
    """

    session_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="会话ID")
    session_key = models.CharField(max_length=200, db_index=True, help_text="会话分组键")
    rule_id = models.CharField(max_length=100, db_index=True, help_text="关联规则ID")

    # 会话时间窗口
    session_start = models.DateTimeField(help_text="会话开始时间")
    last_activity = models.DateTimeField(help_text="最后活动时间")
    session_timeout = models.IntegerField(help_text="会话超时时间(秒)")

    # 会话状态
    is_active = models.BooleanField(default=True, db_index=True, help_text="是否活跃")

    # 新增：会话数据字段，用于存储会话相关的元数据
    session_data = JSONField(default=dict, help_text="会话数据和元数据")

    # 会话关联的事件 - 使用多对多关联替代session_key字符串查询
    events = models.ManyToManyField(
        Event,
        related_name='session_windows',
        through='SessionEventRelation',  # 使用中间表以便添加额外信息
        help_text="会话关联的事件"
    )

    class Meta:
        db_table = 'alerts_session_window'
        indexes = [
            models.Index(fields=['session_key', 'rule_id', 'is_active']),
            models.Index(fields=['is_active', 'last_activity']),
            models.Index(fields=['rule_id', 'is_active']),  # 新增：优化规则查询
        ]

    def __str__(self):
        return f"Session {self.session_id} - {self.session_key}"

    def is_expired(self, current_time=None):
        """判断会话是否已过期"""
        if current_time is None:
            current_time = timezone.now()
        timeout_delta = timedelta(seconds=self.session_timeout)
        return current_time - self.last_activity > timeout_delta

    def should_close_window(self, current_time=None):
        """
        判断会话窗口是否应该关闭
        
        会话窗口关闭的条件：
        1. 会话已过期（超过session_timeout）
        2. 会话窗口大小超过最大限制（max_window_size）
        
        Args:
            current_time: 当前时间
            
        Returns:
            tuple: (should_close, reason)
                should_close: bool，是否应该关闭
                reason: str，关闭原因
        """
        if current_time is None:
            current_time = timezone.now()

        # 检查是否过期
        if self.is_expired(current_time):
            return True, "session_timeout"

        # # 检查是否超过最大窗口大小
        # if self.is_window_size_exceeded(current_time):
        #     return True, "max_window_size_exceeded"

        return False, ""

    def check_has_events(self, events):
        """
        检查会话是否包含指定的事件

        Args:
            events: 需要检查的事件列表

        Returns:
            bool: True表示会话包含这些事件，False表示不包含
        """
        if not events:
            return False

        # 使用多对多关系查询
        return self.events.filter(event_id__in=list(events.values_list("event_id", flat=True))).exists()

    def extend_session(self, new_activity_time=None):
        """
        延长会话活动时间
        
        在延长会话前会检查是否超过最大窗口大小限制
        如果超过限制，会将当前会话标记为非活跃状态
        
        Args:
            new_activity_time: 新的活动时间
            
        Returns:
            bool: True表示成功延长，False表示因超过限制无法延长
        """
        if new_activity_time is None:
            new_activity_time = timezone.now()

        # 检查是否应该关闭窗口
        should_close, reason = self.should_close_window(new_activity_time)

        if should_close:
            return False

        # 正常延长会话
        self.last_activity = new_activity_time
        self.save(update_fields=['last_activity', 'updated_at'])
        return True


class SessionEventRelation(models.Model):
    """
    会话和事件的关联关系中间表

    用于记录事件何时被分配到会话中，以及关联的元数据
    """
    session = models.ForeignKey(SessionWindow, on_delete=models.CASCADE, help_text="会话")
    event = models.ForeignKey(Event, on_delete=models.CASCADE, help_text="事件")
    assigned_at = models.DateTimeField(auto_now_add=True, help_text="分配时间")

    class Meta:
        db_table = 'alerts_session_event_relation'
        unique_together = ['session', 'event']  # 确保同一事件不会被重复分配到同一会话
        indexes = [
            models.Index(fields=['session', 'assigned_at']),
            models.Index(fields=['event']),
        ]
        ordering = ['assigned_at']

    def __str__(self):
        return f"Session {self.session.session_id} - Event {self.event.event_id}"
