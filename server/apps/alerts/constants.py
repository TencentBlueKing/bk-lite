# -- coding: utf-8 --
# @File: constants.py
# @Time: 2025/5/9 14:57
# @Author: windyzhao


class AlertAccessType:
    """告警源接入类型"""
    BUILT_IN = "built_in"
    CUSTOMIZE = "customize"
    CHOICES = (
        (BUILT_IN, "内置"),
        (CUSTOMIZE, "自定义"),
    )


class AlertsSourceTypes:
    """告警源类型"""
    PROMETHEUS = "prometheus"
    ZABBIX = "zabbix"
    WEBHOOK = "webhook"
    LOG = "log"
    MONITOR = "monitor"
    CLOUD = "cloud"
    NATS = "nats"
    RESTFUL = "restful"
    CHOICES = (
        (PROMETHEUS, 'Prometheus'),
        (ZABBIX, 'Zabbix'),
        (WEBHOOK, 'Webhook'),
        (LOG, '日志'),
        (MONITOR, '监控'),
        (CLOUD, '云监控'),
        (NATS, 'NATS'),
        (RESTFUL, 'RESTFul'),
    )


class EventLevel:
    """事件级别"""
    REMAIN = "remain"
    WARNING = "warning"
    SEVERITY = "severity"
    FATAL = "fatal"

    CHOICES = (
        (REMAIN, "提醒"),
        (WARNING, "预警"),
        (SEVERITY, "严重"),
        (FATAL, "致命")
    )


class EventStatus:
    """事件状态"""
    RECEIVED = "received"
    PENDING = "pending"
    RESOLVED = "resolved"
    PROCESSING = "processing"
    CLOSED = "closed"
    SHIELD = "shield"

    CHOICES = (
        (PENDING, "待响应"),
        (PROCESSING, "处理中"),
        (RESOLVED, "已处理"),
        (CLOSED, "已关闭"),
        (SHIELD, "已屏蔽"),
        (RECEIVED, "已接收"),
    )


class EventAction:
    """告警类型"""
    CREATED = "created"
    CLOSED = "closed"

    CHOICES = (
        (CREATED, "产生"),
        (CLOSED, "关闭"),
    )


class AlertLevel:
    """告警级别"""
    WARNING = "warning"
    SEVERITY = "severity"
    FATAL = "fatal"

    CHOICES = (
        (WARNING, "预警"),
        (SEVERITY, "严重"),
        (FATAL, "致命")
    )


class AlertStatus:
    """告警状态"""
    PENDING = "pending"
    RESOLVED = "resolved"
    PROCESSING = "processing"
    CLOSED = "closed"
    UNASSIGNED = "unassigned"
    AUTO_CLOSE = "auto_close"

    CHOICES = (
        (PENDING, "待响应"),
        (PROCESSING, "处理中"),
        (RESOLVED, "已处理"),
        (CLOSED, "已关闭"),
        (UNASSIGNED, "未分派"),
        (AUTO_CLOSE, "自动关闭"),
    )
    ACTIVATE_STATUS = (PENDING, PROCESSING, UNASSIGNED)
    CLOSED_STATUS = (CLOSED, AUTO_CLOSE)


class AlertOperate:
    """告警操作"""
    ACKNOWLEDGE = "acknowledge"
    CLOSE = "close"
    REASSIGN = "reassign"
    ASSIGN = "assign"

    CHOICES = (
        (ACKNOWLEDGE, "认领"),
        (CLOSE, "关闭"),
        (REASSIGN, "转派"),
        (ASSIGN, "分派"),
    )


class IncidentStatus:
    """事故状态"""
    PENDING = "pending"
    RESOLVED = "resolved"
    PROCESSING = "processing"
    CLOSED = "closed"

    CHOICES = (
        (PENDING, "待响应"),
        (PROCESSING, "处理中"),
        (RESOLVED, "已处理"),
        (CLOSED, "已关闭"),
    )
    ACTIVATE_STATUS = (PENDING, PROCESSING)


class IncidentOperate:
    """事故操作"""
    ACKNOWLEDGE = "acknowledge"
    CLOSE = "close"
    REASSIGN = "reassign"
    ASSIGN = "assign"  # 修正拼写错误

    CHOICES = (
        (ACKNOWLEDGE, "认领"),
        (CLOSE, "关闭"),
        (REASSIGN, "转派"),
        (ASSIGN, "分派"),  # 修正拼写错误
    )


# ===
class LevelType:
    """级别类型"""
    EVENT = "event"
    ALERT = "alert"
    INCIDENT = "incident"

    CHOICES = (
        (EVENT, "事件"),
        (ALERT, "告警"),
        (INCIDENT, "事故"),
    )


DEFAULT_LEVEL = [
    {
        "level_type": LevelType.EVENT,
        "level_id": 0,
        "level_name": "Critical",
        "level_display_name": "致命",
        "color": "#F43B2C",
        "icon": "huoyanhuodongtuijian",
        "description": "",
    },
    {
        "level_type": LevelType.EVENT,
        "level_id": 1,
        "level_name": "Error",
        "level_display_name": "错误",
        "color": "#D97007",
        "icon": "weiwangguanicon-defuben-",
        "description": "",
    },
    {
        "level_type": LevelType.EVENT,
        "level_id": 2,
        "level_name": "Warning",
        "level_display_name": "预警",
        "color": "#FFAD42",
        "icon": "gantanhao1",
        "description": "",
    },
    {
        "level_type": LevelType.EVENT,
        "level_id": 3,
        "level_name": "Info",
        "level_display_name": "提醒",
        "color": "#FBBF24",
        "icon": "tixing",
        "description": "",
    },

    {
        "level_type": LevelType.ALERT,
        "level_id": 0,
        "level_name": "Critical",
        "level_display_name": "致命",
        "color": "#F43B2C",
        "icon": "huoyanhuodongtuijian",
        "description": "",
    },
    {
        "level_type": LevelType.ALERT,
        "level_id": 1,
        "level_name": "Error",
        "level_display_name": "错误",
        "color": "#D97007",
        "icon": "weiwangguanicon-defuben-",
        "description": "",
    },
    {
        "level_type": LevelType.ALERT,
        "level_id": 2,
        "level_name": "Warning",
        "level_display_name": "预警",
        "color": "#FFAD42",
        "icon": "gantanhao1",
        "description": "",
    },
    {
        "level_type": LevelType.INCIDENT,
        "level_id": 0,
        "level_name": "Critical",
        "level_display_name": "致命",
        "color": "#F43B2C",
        "icon": "huoyanhuodongtuijian",
        "description": "",
    },
    {
        "level_type": LevelType.INCIDENT,
        "level_id": 1,
        "level_name": "Error",
        "level_display_name": "错误",
        "color": "#D97007",
        "icon": "weiwangguanicon-defuben-",
        "description": "",
    },
    {
        "level_type": LevelType.INCIDENT,
        "level_id": 2,
        "level_name": "Warning",
        "level_display_name": "预警",
        "color": "#FFAD42",
        "icon": "gantanhao1",
        "description": "",
    }

]


class AlertAssignmentMatchType:
    """告警分派匹配类型"""
    ALL = "all"
    FILTER = "filter"

    CHOICES = (
        (ALL, "全部匹配"),
        (FILTER, "过滤匹配"),
    )


class AlertAssignmentNotifyChannels:
    """告警分派通知渠道"""
    EMAIL = "email"
    ENTERPRISE_WECHAT = "enterprise_wechat"

    CHOICES = (
        (EMAIL, "邮件"),
        (ENTERPRISE_WECHAT, "企业微信"),
    )


class AlertAssignmentNotificationScenario:
    """ 告警分派通知场景 """

    ASSIGNMENT = "assignment"
    RECOVERED = "recovered"

    CHOICES = (
        (ASSIGNMENT, "分派"),
        (RECOVERED, "恢复"),
    )


class AlertShieldMatchType:
    """告警屏蔽匹配类型"""
    ALL = "all"
    FILTER = "filter"

    CHOICES = (
        (ALL, "全部匹配"),
        (FILTER, "过滤匹配"),
    )


class CorrelationRulesScope:
    """关联规则作用范围"""
    ALL = "all"
    FILTER = "filter"

    CHOICES = (
        (ALL, "全部匹配"),
        (FILTER, "过滤匹配"),
    )


class CorrelationRulesType:
    """规则适用类型"""
    ALERT = "alert"
    EVENT = "event"

    CHOICES = (
        (ALERT, "告警"),
        (EVENT, "事件"),
    )


class AggregationRuleType:
    """规则适用类型"""
    ALERT = "alert"
    INCIDENT = "incident"

    CHOICES = (
        (ALERT, "告警"),
        (INCIDENT, "事故"),
    )


class NotifyResultStatus:
    """通知结果"""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL_SUCCESS = "partial_success"

    CHOICES = (
        (SUCCESS, "成功"),
        (FAILED, "失败"),
        (PARTIAL_SUCCESS, "部分成功"),
    )


class LogTargetType:
    """
    日志目标类型
    """
    EVENT = "event"
    ALERT = "alert"
    INCIDENT = "incident"
    SYSTEM = "system"
    CHOICES = (
        (EVENT, "事件"),
        (ALERT, "告警"),
        (INCIDENT, "事故"),
        (SYSTEM, "系统"),
    )


class LogAction:
    """
    日志操作类型
    """
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"
    EXECUTE = "execute"
    CHOICES = (
        (ADD, "添加"),
        (MODIFY, "修改"),
        (DELETE, "删除"),
        (EXECUTE, "执行")
    )


class WindowType:
    """
    窗口类型
    """
    SLIDING = "sliding"
    FIXED = "fixed"
    SESSION = "session"

    CHOICES = (
        (SLIDING, '滑动窗口'),
        (FIXED, '固定窗口'),
        (SESSION, '会话窗口'),
    )


class Alignment:
    """
    窗口对齐方式
    """
    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"

    CHOICES = (
        (DAY, '天对齐'),
        (HOUR, '小时对齐'),
        (MINUTE, '分钟对齐'),
    )
