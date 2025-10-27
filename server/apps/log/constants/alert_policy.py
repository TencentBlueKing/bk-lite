class AlertConstants:
    """告警相关常量"""

    # 告警状态
    STATUS_NEW = "new"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, "活跃"),
        (STATUS_CLOSED, "关闭"),
    ]

    # 告警类型
    TYPE_KEYWORD = "keyword"
    TYPE_AGGREGATE = "aggregate"
    ALERT_TYPE = [TYPE_KEYWORD, TYPE_AGGREGATE]

    # 告警级别
    LEVEL_INFO = "info"
    LEVEL_WARNING = "warning"
    LEVEL_ERROR = "error"
    LEVEL_CRITICAL = "critical"
