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


class AlertStrategyType:
    """告警策略类型
    
    定义了六种告警策略类型，每种策略适用于不同的监控场景：
    
    1. THRESHOLD（阈值告警）- 最常用的告警类型
       适用场景：监控指标超过固定阈值时触发告警
       配置示例：CPU使用率 > 80%，内存使用 > 90%
       
    2. MUTATION（突变告警）- 检测指标急剧变化
       适用场景：短时间内指标发生异常波动
       配置示例：QPS在5分钟内增长50%以上，延迟突增200%
       
    3. COMPOSITE（复合条件）- 多条件组合判断
       适用场景：需要同时满足多个条件才触发告警
       配置示例：CPU > 80% AND 内存 > 90% AND 磁盘IO > 1000
       
    4. FREQUENCY（频率告警）- 基于事件发生频次
       适用场景：一定时间内事件发生次数超过阈值
       配置示例：5分钟内登录失败超过10次，1小时内接口报错超过100次
       
    5. TREND（趋势告警）- 预测性告警，基于历史数据趋势分析
       适用场景：通过历史趋势预测未来可能发生的问题
       配置示例：磁盘使用量持续上升，预计3天后将耗尽
       实现状态：待实现，需要结合时序数据库和趋势分析算法
       
    6. ANOMALY（异常检测）- 智能异常检测
       适用场景：基于统计学方法检测偏离正常模式的异常数据
       配置示例：使用Z-Score检测CPU使用率异常波动
       实现状态：待实现，需要结合机器学习模型
    """
    THRESHOLD = "threshold"         # 阈值告警：基于数值阈值判断
    MUTATION = "mutation"           # 突变告警：基于变化率检测
    COMPOSITE = "composite"         # 复合条件：多条件组合逻辑
    FREQUENCY = "frequency"         # 频率告警：基于事件频次
    TREND = "trend"                 # 趋势告警：基于数据趋势分析（待实现）
    ANOMALY = "anomaly"             # 异常检测：基于统计异常（待实现）

    CHOICES = (
        (THRESHOLD, "阈值告警"),
        (MUTATION, "突变告警"), 
        (COMPOSITE, "复合条件"),
        (FREQUENCY, "频率告警"),
        (TREND, "趋势告警"),
        (ANOMALY, "异常检测"),
    )

    @classmethod
    def get_description(cls, strategy_type):
        """获取策略类型的详细描述
        
        Args:
            strategy_type: 策略类型标识
            
        Returns:
            str: 策略类型的详细描述
        """
        descriptions = {
            cls.THRESHOLD: "当监控指标超过设定阈值时触发告警。适用于CPU、内存、磁盘等资源类监控指标。",
            cls.MUTATION: "当监控指标在短时间内发生剧烈变化时触发告警。适用于检测流量突增、性能骤降等异常情况。",
            cls.COMPOSITE: "满足多个复合条件时触发告警，支持AND/OR逻辑组合。适用于需要多维度综合判断的复杂场景。",
            cls.FREQUENCY: "当特定事件在时间窗口内出现频次超过阈值时触发告警。适用于登录失败、接口报错等事件类监控。",
            cls.TREND: "基于历史数据趋势，预测性检测异常情况。适用于容量规划、资源增长预警等场景。（功能开发中）",
            cls.ANOMALY: "使用统计方法检测偏离正常模式的异常数据点。适用于智能化运维场景。（功能开发中）"
        }
        return descriptions.get(strategy_type, "未知策略类型")
    
    @classmethod
    def get_config_template(cls, strategy_type):
        """获取策略类型的配置模板
        
        Args:
            strategy_type: 策略类型标识
            
        Returns:
            dict: 策略配置模板
        """
        templates = {
            cls.THRESHOLD: {
                "metric_field": "value",
                "threshold_value": 80,
                "operator": ">=",
                "duration_minutes": 1,
                "description": "指标字段名、阈值、比较操作符、持续时间"
            },
            cls.MUTATION: {
                "metric_field": "value",
                "change_rate_threshold": 50.0,
                "comparison_window_minutes": 5,
                "change_type": "percent",
                "direction": "both",
                "description": "指标字段名、变化率阈值(%)、对比窗口、变化类型、突变方向"
            },
            cls.COMPOSITE: {
                "conditions": [],
                "logic_operator": "AND",
                "evaluation_window_minutes": 5,
                "description": "条件列表、逻辑操作符(AND/OR)、评估窗口"
            },
            cls.FREQUENCY: {
                "event_count_threshold": 10,
                "time_window_minutes": 5,
                "group_by_fields": ["resource_type", "resource_name"],
                "description": "事件数量阈值、时间窗口、分组字段"
            },
            cls.TREND: {
                "metric_field": "value",
                "trend_direction": "upward",
                "slope_threshold": 0.1,
                "data_points": 5,
                "confidence_level": 0.8,
                "description": "指标字段名、趋势方向、斜率阈值、数据点数、置信度（待实现）"
            },
            cls.ANOMALY: {
                "metric_field": "value",
                "detection_method": "zscore",
                "sensitivity": 2.0,
                "baseline_window_minutes": 60,
                "min_baseline_samples": 10,
                "description": "指标字段名、检测方法、敏感度、基线窗口、最小样本数（待实现）"
            }
        }
        return templates.get(strategy_type, {})


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
