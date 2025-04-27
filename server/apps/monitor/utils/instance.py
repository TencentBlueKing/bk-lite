from datetime import datetime, timezone


def calculation_status(data_time: int):
    """计算状态"""

    if not data_time:
        return ""

    # 获取当前时间时间戳，utc0时区的
    now_timestamp = int(datetime.now(timezone.utc).timestamp())
    # 计算时间差
    time_diff = now_timestamp - data_time
    # 5分钟内正常，1小时内不活跃，1小时以上异常
    if time_diff < 300:
        return "normal"
    elif time_diff < 3600:
        return "inactive"
    else:
        return "unavailable"
