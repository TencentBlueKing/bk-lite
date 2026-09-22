class AlertConstants:
    """告警相关常量"""

    # 补偿机制配置
    MAX_BACKFILL_COUNT = 30  # 累计最多补偿的周期数（落后更多的窗口不再补偿）
    MAX_BACKFILL_SECONDS = (
        24 * 3600
    )  # 最大补偿时间范围（秒），超过此范围的历史数据不再补偿
    # 单次 scan_policy_task 内最多连续补偿的窗口数；剩余窗口由下一次 Beat 调度继续。
    # 每个窗口都会重建扫描器并拉一轮 VM 数据，prefork worker 的 RSS 不会随窗口释放。
    MAX_BACKFILL_PER_TASK = 3
    # 补偿循环的软时限（秒）：超过后不再开启新窗口，已开始的窗口正常完成。
    BACKFILL_SOFT_TIME_LIMIT_SECONDS = 45

    # 策略扫描把实例范围编进 PromQL selector 时，每批最多携带的实例数；
    # 超过则拆成多次查询后合并，避免拼出超长正则。
    SCAN_SCOPE_BATCH_SIZE = 200

    # 阈值对比方法
    THRESHOLD_METHODS = {
        ">": lambda x, y: x > y,
        "<": lambda x, y: x < y,
        "=": lambda x, y: x == y,
        "!=": lambda x, y: x != y,
        ">=": lambda x, y: x >= y,
        "<=": lambda x, y: x <= y,
    }

    # 告警等级权重
    LEVEL_WEIGHT = {
        "warning": 2,
        "error": 3,
        "critical": 4,
        "no_data": 5,
    }

    # 阈值告警类型
    THRESHOLD = "threshold"
    # 无数据告警类型
    NO_DATA = "no_data"
