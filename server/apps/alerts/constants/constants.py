# -- coding: utf-8 --
# @File: constants.py
# @Time: 2025/5/9 14:57
# @Author: windyzhao

SYSTEM_OPERATOR_USER = "admin"

# SNMP Trap 暂不参与组织级 secret 路由：bridge 用源级 secret 接入，事件统一归默认组织。
SNMP_TRAP_SOURCE_ID = "snmp_trap"
# Default 组 ID 由 system_mgmt 的 clean_group_data 强制保证为 1（如不为 1 会自动迁移）。
DEFAULT_GROUP_ID = 1

PERMISSION_EVENT = "event"
PERMISSION_ALERT = "alert"
PERMISSION_INCIDENT = "incident"


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
        (PROMETHEUS, "Prometheus"),
        (ZABBIX, "Zabbix"),
        (WEBHOOK, "Webhook"),
        (LOG, "日志"),
        (MONITOR, "监控"),
        (CLOUD, "云监控"),
        (NATS, "NATS"),
        (RESTFUL, "RESTFul"),
    )


class EventLevel:
    """事件级别"""

    REMAIN = "remain"
    WARNING = "warning"
    SEVERITY = "severity"
    FATAL = "fatal"

    CHOICES = ((REMAIN, "提醒"), (WARNING, "预警"), (SEVERITY, "严重"), (FATAL, "致命"))


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
    RECOVERY = "recovery"

    CHOICES = (
        (CREATED, "产生"),
        (CLOSED, "关闭"),
        (RECOVERY, "恢复"),
    )


class EventType:
    """
    事件类型
    """

    ALERT = 0
    RECOVERY = 1

    CHOICES = (
        (ALERT, "告警事件"),
        (RECOVERY, "恢复事件"),
    )


class AlertStatus:
    """告警状态"""

    PENDING = "pending"
    RESOLVED = "resolved"
    PROCESSING = "processing"
    CLOSED = "closed"
    UNASSIGNED = "unassigned"
    AUTO_CLOSE = "auto_close"
    AUTO_RECOVERY = "auto_recovery"

    CHOICES = (
        (PENDING, "待响应"),
        (PROCESSING, "处理中"),
        (RESOLVED, "已处理"),
        (CLOSED, "已关闭"),
        (UNASSIGNED, "未分派"),
        (AUTO_CLOSE, "自动关闭"),
        (AUTO_RECOVERY, "自动恢复"),
    )
    ACTIVATE_STATUS = (PENDING, PROCESSING, UNASSIGNED)
    CLOSED_STATUS = (CLOSED, AUTO_CLOSE, AUTO_RECOVERY)


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


class SessionStatus:
    """会话Alert状态,observing是观察中的虚拟alert，实际并不是alert；recovered是虚拟alert还未转正就恢复了"""

    OBSERVING = "observing"
    CONFIRMED = "confirmed"
    RECOVERED = "recovered"

    CHOICES = (
        (OBSERVING, "观察中"),
        (CONFIRMED, "已确认"),
        (RECOVERED, "已恢复"),
    )
    NO_CONFIRMED = (OBSERVING, RECOVERED)


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


class AlertAssignmentMatchType:
    """告警分派匹配类型"""

    ALL = "all"
    FILTER = "filter"

    CHOICES = (
        (ALL, "全部匹配"),
        (FILTER, "过滤匹配"),
    )


class AlertAssignmentNotificationScenario:
    """告警分派通知场景"""

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


class AlarmStrategyType:
    SMART_DENOISE = "smart_denoise"
    MISSING_DETECTION = "missing_detection"
    INSTANT = "instant"

    CHOICES = (
        (SMART_DENOISE, "智能降噪"),
        (MISSING_DETECTION, "缺失检测"),
        (INSTANT, "即时告警"),
    )


# 即时告警旁路：命中数 ≤ 阈值在 adapter 线程内同步落库；> 阈值入 Celery 队列
INSTANT_SYNC_THRESHOLD = 50
# 单次 dispatch 命中数上限（防异常事件源刷爆）
INSTANT_HIT_CEILING = 5000
# 即时告警策略缓存 TTL（秒）
INSTANT_STRATEGY_CACHE_TTL = 60


class HeartbeatCheckMode:
    CRON = "cron"

    CHOICES = ((CRON, "Cron 表达式"),)


class HeartbeatActivationMode:
    FIRST_HEARTBEAT = "first_heartbeat"
    IMMEDIATE = "immediate"

    CHOICES = (
        (FIRST_HEARTBEAT, "首条心跳激活"),
        (IMMEDIATE, "立即激活"),
    )


class HeartbeatStatus:
    WAITING = "waiting"
    MONITORING = "monitoring"
    ALERTING = "alerting"

    CHOICES = (
        (WAITING, "待激活"),
        (MONITORING, "监控中"),
        (ALERTING, "缺失告警中"),
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


class IncidentUpdateType:
    """协作更新类型"""

    OBSERVATION = "observation"
    PROGRESS = "progress"
    CONCLUSION = "conclusion"
    NEXT_STEP = "next_step"

    CHOICES = (
        (OBSERVATION, "观察"),
        (PROGRESS, "进展"),
        (CONCLUSION, "结论"),
        (NEXT_STEP, "下一步"),
    )


class LogAction:
    """
    日志操作类型
    """

    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"
    EXECUTE = "execute"
    CHOICES = ((ADD, "添加"), (MODIFY, "修改"), (DELETE, "删除"), (EXECUTE, "执行"))


class WindowType:
    """
    窗口类型
    """

    SLIDING = "sliding"
    FIXED = "fixed"
    SESSION = "session"

    CHOICES = (
        (SLIDING, "滑动窗口"),
        (FIXED, "固定窗口"),
        (SESSION, "会话窗口"),
    )


class Alignment:
    """
    窗口对齐方式
    """

    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"

    CHOICES = (
        (DAY, "天对齐"),
        (HOUR, "小时对齐"),
        (MINUTE, "分钟对齐"),
    )
