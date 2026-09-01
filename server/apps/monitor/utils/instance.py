from datetime import datetime, timezone

NORMAL_REPORT_WINDOW_SECONDS = 300
# 列表「正常 / 失联」：最后上报超过 10 分钟视为失联。
LIST_UNAVAILABLE_AFTER_SECONDS = 600


def calculation_status(data_time: int):
    """计算状态"""

    if not data_time:
        return ""

    # 获取当前时间时间戳，utc0时区的
    now_timestamp = int(datetime.now(timezone.utc).timestamp())
    # 计算时间差
    time_diff = now_timestamp - data_time
    # 5分钟内正常，1小时内不活跃，1小时以上异常
    if time_diff < NORMAL_REPORT_WINDOW_SECONDS:
        return "normal"
    elif time_diff < 3600:
        return "inactive"
    else:
        return "unavailable"


def last_sample_unix_seconds_or_none(data_time):
    """把列表里的上报时间收成 Unix 秒；空值、非时间数字直接丢掉。"""
    if data_time in (None, ""):
        return None
    if isinstance(data_time, bool):
        return None
    if isinstance(data_time, (int, float)):
        timestamp = float(data_time)
        return timestamp if timestamp > 0 else None
    if isinstance(data_time, str):
        try:
            timestamp = float(data_time)
        except ValueError:
            try:
                timestamp = datetime.fromisoformat(data_time.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None
        return timestamp if timestamp > 0 else None
    return None


def list_reporting_status(data_time):
    """列表上报状态只区分正常/失联：最后上报超过 10 分钟即为失联。"""
    timestamp = last_sample_unix_seconds_or_none(data_time)
    if timestamp is None:
        return "unavailable"
    now_timestamp = int(datetime.now(timezone.utc).timestamp())
    if now_timestamp - int(timestamp) < LIST_UNAVAILABLE_AFTER_SECONDS:
        return "normal"
    return "unavailable"
