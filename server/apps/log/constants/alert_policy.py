import os


class AlertConstants:
    """告警相关常量"""

    # 补偿机制配置
    MAX_BACKFILL_COUNT = 10  # 每次任务执行最多补偿的周期数
    MAX_BACKFILL_SECONDS = 24 * 3600  # 最大补偿时间范围（秒）
    INGEST_DELAY_SECONDS = 60  # 日志查询安全延迟（秒）
    WINDOW_OVERLAP_SECONDS = 0  # 预留窗口重叠能力，当前默认关闭避免重复事件

    # 通知发送可靠性配置（均给保守默认 + env 可调，详见 PR 说明）
    # A 内联重试：单次发送遇瞬时通道故障时的总尝试次数（含首发）
    NOTICE_SEND_MAX_ATTEMPTS = int(os.getenv("LOG_NOTICE_SEND_MAX_ATTEMPTS", "3"))
    NOTICE_SEND_RETRY_BACKOFF_SECONDS = float(os.getenv("LOG_NOTICE_SEND_RETRY_BACKOFF_SECONDS", "1"))
    # B 持久化补偿：周期任务回扫近期发送失败事件重投
    NOTICE_COMPENSATE_MAX_RETRY = int(os.getenv("LOG_NOTICE_COMPENSATE_MAX_RETRY", "5"))  # 单事件最多被补偿重投次数
    NOTICE_COMPENSATE_WINDOW_SECONDS = int(os.getenv("LOG_NOTICE_COMPENSATE_WINDOW_SECONDS", str(24 * 3600)))  # 仅补偿近 N 秒内失败事件
    NOTICE_COMPENSATE_BATCH_SIZE = int(os.getenv("LOG_NOTICE_COMPENSATE_BATCH_SIZE", "200"))  # 单次补偿处理事件数上限
    # 最小 age 门槛：仅补偿落库已超 N 秒的事件，降低与扫描线程同步通知（notice()）并发双投的概率。
    # 默认 600s：notice() 在通道故障下逐事件内联重试，慢路径可达分钟级；
    # 补偿是兜底层，延后无伤大雅，门槛必须大于 notice() 的最坏耗时量级才有效。
    NOTICE_COMPENSATE_MIN_AGE_SECONDS = int(os.getenv("LOG_NOTICE_COMPENSATE_MIN_AGE_SECONDS", "600"))

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

    # 聚合条件函数。count_delta 仍被接受，读写两侧归一为 count + delta + previous_window。
    AGGREGATE_FUNCS = frozenset(
        {
            "count",
            "sum",
            "avg",
            "max",
            "min",
            "count_uniq",
            "quantile",
            "ratio",
            "count_rate",
            "bytes_rate",
        }
    )
    COUNT_DERIVED_FUNCS = frozenset({"count_rate", "count_delta"})
    COMPARE_KINDS = frozenset({"absolute", "delta", "percent"})
    COMPARE_TARGETS = frozenset({"previous_window", "offset_1h", "offset_24h", "offset_7d", "offset_hours", "offset_days"})
    COMPARE_OFFSET_SECONDS = {"offset_1h": 3600, "offset_24h": 86400, "offset_7d": 604800}
    COMPARE_LEGACY_OFFSETS = {"offset_1h": ("offset_hours", 1), "offset_24h": ("offset_hours", 24), "offset_7d": ("offset_days", 7)}
    MAX_COMPARE_OFFSET_HOURS = 8760
    MAX_COMPARE_OFFSET_DAYS = 365
    COMPARABLE_FUNCS = frozenset({"count", "sum", "avg", "max", "min", "count_uniq", "quantile"})
    QUANTILE_CHOICES = (0.5, 0.9, 0.95, 0.99)
    RATIO_FILTER_MAX_LEN = 500
    TRIGGER_COUNT_MAX = 5
    COUNT_UNIQ_LIMIT = 1_000_000
    # 对照窗缺分组时记 0 的函数。均值 / 分位缺分组是「没有值」。
    MISSING_GROUP_ZERO_FUNCS = frozenset({"count", "count_uniq", "sum"})
    SAMPLE_LIMIT_MAX = 10
    DRY_RUN_ITEM_LIMIT = 200
    NOTICE_SAMPLE_TEXT_MAX = 200
