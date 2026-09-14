# -- coding: utf-8 --
"""
Alerts Models

统一导出所有模型类，保持向后兼容
"""

# 动作规则与执行记录
from .action import ActionExecution, ActionRule  # noqa: F401
from .active_fingerprint import ActiveAlertFingerprint  # noqa: F401

# 告警操作相关
from .alert_operator import AlarmStrategy, AlertAssignment, AlertReminderTask, AlertShield, NotifyResult

# 告警源
from .alert_source import AlertSource

# 丰富规则
from .enrichment import EnrichmentRule  # noqa: F401
from .install_token import K8sInstallToken  # noqa: F401

# 事件和告警
from .models import Alert, Event, Incident, IncidentUpdate, Level
from .notification_template import NotificationTemplate, NotificationTemplateContent, NotificationTemplateReference  # noqa: F401

# 操作日志
from .operator_log import OperatorLog
from .outbox import AlertNotificationDelivery, AlertOutbox  # noqa: F401

# 系统设置
from .sys_setting import SystemSetting

__all__ = [
    # 告警源
    "AlertSource",
    # 事件和告警
    "Event",
    "Alert",
    "Incident",
    "IncidentUpdate",
    "Level",
    # 告警操作相关
    "AlertAssignment",
    "AlertShield",
    "AlertReminderTask",
    "AlarmStrategy",
    "NotifyResult",
    # 系统设置
    "SystemSetting",
    # 操作日志
    "OperatorLog",
    # 丰富规则
    "EnrichmentRule",
    # 动作规则与执行记录
    "ActionRule",
    "ActionExecution",
    "ActiveAlertFingerprint",
    "AlertOutbox",
    "AlertNotificationDelivery",
    "K8sInstallToken",
    "NotificationTemplate",
    "NotificationTemplateContent",
    "NotificationTemplateReference",
]
