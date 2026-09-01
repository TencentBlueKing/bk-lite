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
        return f"max(tlast_over_time(({inner})[{window}])) by ({group})"
    return f"tlast_over_time(({trimmed})[{window}])"


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
