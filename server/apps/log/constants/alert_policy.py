class AlertConstants:
    """告警相关常量"""

    # 补偿机制配置
    MAX_BACKFILL_COUNT = 10  # 每次任务执行最多补偿的周期数
    MAX_BACKFILL_SECONDS = 24 * 3600  # 最大补偿时间范围（秒）
    INGEST_DELAY_SECONDS = 60  # 日志查询安全延迟（秒）
    WINDOW_OVERLAP_SECONDS = 0  # 预留窗口重叠能力，当前默认关闭避免重复事件

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
