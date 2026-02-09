# -- coding: utf-8 --
"""
Alerts Views

统一导出所有视图集，保持向后兼容
"""

# 告警源
from .alert_source import AlertSourceModelViewSet

# 告警
from .alert import AlterModelViewSet

# 事件
from .event import EventModelViewSet

# 告警等级
from .level import LevelModelViewSet

# 事故
from .incident import IncidentModelViewSet

# 分派与屏蔽
from .assignment_shield import (
    AlertAssignmentModelViewSet,
    AlertShieldModelViewSet,
)

# 系统设置
from .system_setting import SystemSettingModelViewSet

# 操作日志
from .operator_log import SystemLogModelViewSet

# 策略
from .strategy import AlarmStrategyModelViewSet

# 接收器
from .receiver import receiver_data, request_test

__all__ = [
    # 告警源
    "AlertSourceModelViewSet",
    # 告警
    "AlterModelViewSet",
    # 事件
    "EventModelViewSet",
    # 告警等级
    "LevelModelViewSet",
    # 事故
    "IncidentModelViewSet",
    # 分派与屏蔽
    "AlertAssignmentModelViewSet",
    "AlertShieldModelViewSet",
    # 系统设置
    "SystemSettingModelViewSet",
    # 操作日志
    "SystemLogModelViewSet",
    # 策略
    "AlarmStrategyModelViewSet",
    # 接收器
    "receiver_data",
    "request_test",
]

# @File: __init__.py.py
# @Time: 2025/5/9 14:58
# @Author: windyzhao
