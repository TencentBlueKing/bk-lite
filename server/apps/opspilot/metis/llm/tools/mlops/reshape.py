"""把监控或用户贴出的点收成预测服务能接受的规则序列。"""

import math
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Shanghai"
MAX_STEPS = 500
MIN_HISTORY_FACTOR = 2
MAX_HISTORY_FACTOR = 4
MS_TIMESTAMP = 10**12


def choose_frequency(horizon_days: float) -> tuple[int, int, str]:
    """返回 (频率秒数, steps, 频率标签)。"""
    if not isinstance(horizon_days, (int, float)) or isinstance(horizon_days, bool) or horizon_days <= 0:
        raise ValueError("horizon_days must be a positive number")
    horizon_seconds = float(horizon_days) * 86400
    if horizon_days <= 2:
        frequency = 15 * 60
        label = "15m"
    elif horizon_days <= 7:
        frequency = 3600
        label = "1h"
    elif horizon_days <= 31:
        frequency = 2 * 3600
        label = "2h"
    else:
        raw = math.ceil(horizon_seconds / MAX_STEPS)
        choices = [2 * 3600, 6 * 3600, 12 * 3600, 86400, 2 * 86400, 7 * 86400]
        frequency = next((item for item in choices if item >= raw), math.ceil(raw / 3600) * 3600)
        label = _frequency_label(frequency)
    steps = max(1, math.ceil(horizon_seconds / frequency))
    if horizon_days > 31 and steps > MAX_STEPS:
        steps = MAX_STEPS
    return frequency, steps, label


def normalize_timestamp(value: Any) -> Optional[int]:
    """大于 10^12 的数按毫秒换成 Unix 秒。"""
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text or not _is_number(text):
            return None
        number = int(float(text))
    else:
        return None
    if number > MS_TIMESTAMP:
        return number // 1000
    return number


def prepare_series(points: list, horizon_days: float) -> dict:
    """下采样、截取最近连续段，并给出送给 predict 的 data 与 steps。"""
    frequency, steps, label = choose_frequency(horizon_days)
    normalized = []
    for point in points or []:
        if not isinstance(point, dict):
            continue
        timestamp = normalize_timestamp(point.get("timestamp"))
        value = _as_float(point.get("value"))
        if timestamp is None or value is None:
            continue
        normalized.append((timestamp, value))
    if not normalized:
        return _failure(label, steps, frequency, "没有可用的时序点")

    buckets: dict[int, tuple[int, float]] = {}
    for timestamp, value in normalized:
        bucket = timestamp - (timestamp % frequency)
        current = buckets.get(bucket)
        if current is None or timestamp >= current[0]:
            buckets[bucket] = (timestamp, value)

    ordered = sorted(buckets)
    if not ordered:
        return _failure(label, steps, frequency, "没有可用的时序点")

    start_index = len(ordered) - 1
    while start_index > 0 and ordered[start_index] - ordered[start_index - 1] == frequency:
        start_index -= 1
    continuous = ordered[start_index:]
    gap_text = ""
    if start_index > 0:
        gap_text = f"缺口在 {_format_time(ordered[start_index - 1])} 与 {_format_time(ordered[start_index])} 之间"

    keep = continuous[-MAX_HISTORY_FACTOR * steps :]
    minimum = MIN_HISTORY_FACTOR * steps
    if len(keep) < minimum:
        needed = _duration_text(minimum * frequency)
        detail = f"最近连续历史不足，至少需要 {needed}"
        if gap_text:
            detail = f"{detail}；{gap_text}"
        return _failure(label, steps, frequency, detail)

    data = [{"timestamp": bucket, "value": buckets[bucket][1]} for bucket in keep]
    return {
        "ok": True,
        "frequency": label,
        "frequency_seconds": frequency,
        "steps": steps,
        "data": data,
        "last_timestamp": keep[-1],
        "error": "",
    }


def summarize_prediction(prediction: list, last_timestamp: int, timezone_name: str = DEFAULT_TIMEZONE) -> dict:
    points = []
    for item in prediction or []:
        if not isinstance(item, dict):
            continue
        timestamp = normalize_timestamp(item.get("timestamp"))
        value = _as_float(item.get("value"))
        if timestamp is None or value is None:
            continue
        points.append((timestamp, value))
    if not points:
        return {"error": "预测结果没有可用的点"}
    max_timestamp, max_value = max(points, key=lambda item: item[1])
    final_timestamp, final_value = points[-1]
    zone = _zone(timezone_name)
    return {
        "max_value": max_value,
        "max_time": _format_time(max_timestamp, zone),
        "max_offset": _duration_text(max(0, max_timestamp - last_timestamp)),
        "final_value": final_value,
        "final_time": _format_time(final_timestamp, zone),
        "final_offset": _duration_text(max(0, final_timestamp - last_timestamp)),
        "trend": [{"timestamp": timestamp, "time": _format_time(timestamp, zone), "value": value} for timestamp, value in points],
    }


def series_identity(labels: dict) -> str:
    items = []
    for key, value in sorted((labels or {}).items()):
        if key == "__name__" or value in (None, ""):
            continue
        items.append(f"{key}={value}")
    return ",".join(items)


def _failure(label: str, steps: int, frequency: int, error: str) -> dict:
    return {
        "ok": False,
        "frequency": label,
        "frequency_seconds": frequency,
        "steps": steps,
        "data": [],
        "last_timestamp": None,
        "error": error,
    }


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or not _is_number(text):
            return None
        return float(text)
    return None


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _frequency_label(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    return f"{seconds // 60}m"


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _format_time(timestamp: int, zone: Optional[ZoneInfo] = None) -> str:
    zone = zone or ZoneInfo(DEFAULT_TIMEZONE)
    return datetime.fromtimestamp(timestamp, zone).strftime("%Y-%m-%d %H:%M")


def _duration_text(seconds: int) -> str:
    seconds = int(seconds)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _rest = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if minutes or not parts:
        parts.append(f"{minutes}分钟")
    return "".join(parts)
