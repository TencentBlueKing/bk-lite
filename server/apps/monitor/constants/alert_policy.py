class AlertConstants:
    """告警相关常量"""

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

