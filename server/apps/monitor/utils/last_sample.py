"""监控实例列表的最近上报样本时间。

VictoriaMetrics 即时查询的 ``value[0]`` 是求值时刻，不是样本自己的时间。
``any(...) by (...)`` 这类聚合再包 ``timestamp()`` 也仍会落到求值时刻。
列表上报时间必须对原始选择器做 ``tlast_over_time``，从 ``value[1]`` 取最后一条原始样本时间。
"""

from __future__ import annotations

import re

LAST_SAMPLE_LOOKBACK = "20m"
# 低于此值更像指标值（0/1/百分比）而不是 Unix 秒，拒绝以免把 1970 年当成上报时间。
_MIN_UNIX_SECONDS = 1_000_000_000

_AGG_BY_RE = re.compile(
    r"^\s*(?:any|sum|min|max|avg|count|group)\s*\((?P<inner>.+)\)\s+by\s*\((?P<group>[^)]*)\)\s*$",
    re.IGNORECASE | re.DOTALL,
)
# 已带 lookback 的发现查询（如阿里云 default_metric）再套 tlast 时必须拆掉内层，
# 否则会变成 tlast_over_time((last_over_time(sel[30m]))[20m])，原始样本稍旧时列表直接变空。
_LAST_OVER_TIME_RE = re.compile(
    r"^\s*last_over_time\s*\(\s*(?P<selector>.+?)\[(?P<range>[^\]]+)\]\s*\)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_DURATION_RE = re.compile(r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|s|m|h|d|w|y)\s*$", re.IGNORECASE)
_DURATION_SECONDS = {
    "ms": 0.001,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
    "d": 86400.0,
    "w": 604800.0,
    "y": 31536000.0,
}


def _duration_seconds(duration: str) -> float | None:
    match = _DURATION_RE.match(duration or "")
    if not match:
        return None
    unit = match.group("unit").lower()
    return float(match.group("value")) * _DURATION_SECONDS[unit]


def _longer_lookback(left: str, right: str) -> str:
    """取更长的 lookback；无法解析时保留 left（通常是发现侧窗口）。"""
    left_seconds = _duration_seconds(left)
    right_seconds = _duration_seconds(right)
    if left_seconds is None:
        return right
    if right_seconds is None:
        return left
    return left if left_seconds >= right_seconds else right


def _raw_selector_and_lookback(expr: str, window: str) -> tuple[str, str]:
    """若表达式已是 last_over_time(sel[Xm])，拆出原始选择器并合并 lookback。"""
    match = _LAST_OVER_TIME_RE.match((expr or "").strip())
    if not match:
        return expr, window
    selector = match.group("selector").strip()
    return selector, _longer_lookback(match.group("range").strip(), window)


def last_sample_timestamp_query(query: str, window: str = LAST_SAMPLE_LOOKBACK) -> str:
    """把状态/默认指标查询改写成返回最后一条原始样本时间戳的 MetricsQL。"""
    trimmed = (query or "").strip()
    if not trimmed:
        return trimmed
    if "tlast_over_time" in trimmed.lower():
        return trimmed
    match = _AGG_BY_RE.match(trimmed)
    if match:
        inner = match.group("inner").strip()
        group = match.group("group").strip()
        selector, lookback = _raw_selector_and_lookback(inner, window)
        return f"max(tlast_over_time(({selector})[{lookback}])) by ({group})"
    selector, lookback = _raw_selector_and_lookback(trimmed, window)
    return f"tlast_over_time(({selector})[{lookback}])"


def last_sample_unix_seconds(sample: dict | None) -> float | None:
    """从 ``tlast_over_time`` / ``timestamp()`` 结果取最后样本 Unix 秒。"""
    value = (sample or {}).get("value") or []
    if len(value) < 2:
        return None
    try:
        timestamp = float(value[1])
    except (TypeError, ValueError):
        return None
    if timestamp < _MIN_UNIX_SECONDS:
        return None
    return timestamp
