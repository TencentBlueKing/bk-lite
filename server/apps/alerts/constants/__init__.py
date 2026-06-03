# -- coding: utf-8 --
"""
Alerts Constants

统一导出所有常量类，保持向后兼容
"""

from .constants import (
    PERMISSION_EVENT,
    PERMISSION_ALERT,
    PERMISSION_INCIDENT,
    # 告警源相关
    AlertAccessType,
    AlertsSourceTypes,
    # 事件相关
    EventLevel,
    EventStatus,
    EventAction,
    EventType,
    # 告警相关
    AlertStatus,
    AlertOperate,
    SessionStatus,
    # 事故相关
    IncidentStatus,
    IncidentOperate,
    # 等级类型
    LevelType,
    # 分派相关
    AlertAssignmentMatchType,
    AlertAssignmentNotificationScenario,
    # 屏蔽相关
    AlertShieldMatchType,
    # 策略相关
    AlarmStrategyType,
    HeartbeatCheckMode,
    HeartbeatActivationMode,
    HeartbeatStatus,
    # 通知相关
    NotifyResultStatus,
    # 日志相关
    LogTargetType,
    LogAction,
    # 窗口相关
    WindowType,
    Alignment,
    # 即时告警旁路
    INSTANT_SYNC_THRESHOLD,
    INSTANT_HIT_CEILING,
    INSTANT_STRATEGY_CACHE_TTL,
)

__all__ = [
    "PERMISSION_EVENT",
    "PERMISSION_ALERT",
    "PERMISSION_INCIDENT",
    # 告警源相关
    "AlertAccessType",
    "AlertsSourceTypes",
    # 事件相关
    "EventLevel",
    "EventStatus",
    "EventAction",
    "EventType",
    # 告警相关
    "AlertStatus",
    "AlertOperate",
    "SessionStatus",
    # 事故相关
    "IncidentStatus",
    "IncidentOperate",
    # 等级类型
    "LevelType",
    # 分派相关
    "AlertAssignmentMatchType",
    "AlertAssignmentNotificationScenario",
    # 屏蔽相关
    "AlertShieldMatchType",
    # 策略相关
    "AlarmStrategyType",
    "HeartbeatCheckMode",
    "HeartbeatActivationMode",
    "HeartbeatStatus",
    # 通知相关
    "NotifyResultStatus",
    # 日志相关
    "LogTargetType",
    "LogAction",
    # 窗口相关
    "WindowType",
    "Alignment",
    # 即时告警旁路
    "INSTANT_SYNC_THRESHOLD",
    "INSTANT_HIT_CEILING",
    "INSTANT_STRATEGY_CACHE_TTL",
]
