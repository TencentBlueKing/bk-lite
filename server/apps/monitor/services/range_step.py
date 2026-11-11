"""query_range 步长。

VictoriaMetrics 的 ``/api/v1/query_range`` 在 ``[start, end]`` 上按 step 取点，
两端都包含，点数上界是 ``floor((end - start) / step) + 1``。起止若再向 step
边界对齐，实际点数只会少不会多，所以用这个上界做预算。

未传 step 时从现有默认 5m 起，沿阶梯取最细的一档，使上界不超过
``MAX_AUTO_RANGE_POINTS``。短窗口因此仍是 5m，不会比现在更密。显式 step
交给 ``normalize_step``，可以比 5m 更细。

instant 的 ``avg_over_time`` 不走这里。子查询分辨率仍是 5m（或调用方显式
step），窗口平均的采样密度不变。
"""

from __future__ import annotations

import math

MAX_AUTO_RANGE_POINTS = 1000

# 5m 是历史默认值，也是自动档的下限。15m 用来接住 7 天：10m 的闭区间点数是
# floor(604800/600)+1 = 1009，会越过上限；若直接跳到 30m 只剩 337 点，峰值损失更大。
_AUTO_RANGE_STEP_LADDER: tuple[tuple[int, str], ...] = (
    (300, "5m"),
    (600, "10m"),
    (900, "15m"),
    (1800, "30m"),
    (3600, "1h"),
    (7200, "2h"),
    (21600, "6h"),
    (86400, "1d"),
    (604800, "7d"),
)


def query_range_point_count(duration_seconds: float, step_seconds: int) -> int:
    """闭区间 query_range 的点数上界。

    窗长先向上取整到秒。起止各自截成 Unix 秒时，实际窗口最多比
    ``total_seconds()`` 多出不到 1 秒；不取整会把 1000 点的边界算成 1001。
    """
    if step_seconds <= 0:
        raise ValueError("step must be greater than 0")
    if duration_seconds <= 0:
        return 1
    duration = math.ceil(duration_seconds)
    return duration // step_seconds + 1


def _fallback_step_label(duration_seconds: int) -> str:
    """阶梯最后一档仍超过点数上限时，按秒向上取整。"""
    slots = MAX_AUTO_RANGE_POINTS - 1
    step_seconds = max(1, math.ceil(duration_seconds / slots))
    step_seconds = max(step_seconds, _AUTO_RANGE_STEP_LADDER[-1][0])
    return f"{step_seconds}s"


def auto_range_step(duration_seconds: float) -> str:
    """按窗长选择自动 step。窗长非正时退回 5m。"""
    if duration_seconds <= 0:
        return "5m"
    for step_seconds, label in _AUTO_RANGE_STEP_LADDER:
        if query_range_point_count(duration_seconds, step_seconds) <= MAX_AUTO_RANGE_POINTS:
            return label
    return _fallback_step_label(math.ceil(duration_seconds))


def explicit_range_step(explicit_step: object) -> str | None:
    """省略或非正 step 视为未提供；其它值交给 normalize_step。"""
    if explicit_step in (None, ""):
        return None
    if isinstance(explicit_step, bool):
        raise ValueError("step format is invalid")
    if isinstance(explicit_step, (int, float)) and explicit_step <= 0:
        return None
    text = str(explicit_step).strip()
    if text.startswith("-"):
        return None
    from apps.monitor.services.metrics import Metrics
    from apps.monitor.services.nats_query_contract import normalize_step

    try:
        seconds = Metrics.parse_step_to_seconds(explicit_step)
    except ValueError as exc:
        if "greater than 0" in str(exc):
            return None
        raise
    if seconds <= 0:
        return None
    return normalize_step(explicit_step)


def resolve_range_step(duration_seconds: float, explicit_step: object = None) -> str:
    """显式 step 优先；空值或非正值按窗长自动选择。"""
    normalized = explicit_range_step(explicit_step)
    if normalized is None:
        return auto_range_step(duration_seconds)
    return normalized
