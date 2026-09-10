"""Zombie host report folding and threshold helpers.

NATS stays in Task 5. This module is query-free and Django-free so thresholds,
IO max-per-disk, and inst_uuid caps can be unit-tested in isolation.

Metric query templates join Linux and Windows WMI with `or`, matching
`dashboard_query_capabilities` host CPU/mem. Task 5 substitutes `__$labels__`
and wraps avg_over_time / max_over_time using `range_window`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping

from apps.monitor.services.metric_series import window_selector

MAX_HOSTS = 100
UNBOUNDED = -1
LOGIN_STATUS_UNCOLLECTED = "uncollected"

# 7 天窗口下的闲机/可降配口径：CPU 持续很低、入包接近空闲、登录几乎没有。
# -1 仍表示该边界不限；不随时间窗缩放。
DEFAULT_THRESHOLDS = {
    "login_min": -1,
    "login_max": 2,
    "packets_recv_max_min": -1,
    "packets_recv_max_max": 200,
    "packets_recv_avg_min": -1,
    "packets_recv_avg_max": 50,
    "cpu_avg_min": -1,
    "cpu_avg_max": 8,
    "cpu_max_min": -1,
    "cpu_max_max": 20,
    "mem_avg_min": -1,
    "mem_avg_max": 25,
    "mem_max_min": -1,
    "mem_max_max": 40,
    "io_max_min": -1,
    "io_max_max": 10,
}

FOLD_IDENTITY = "identity"
FOLD_SUM = "sum"
FOLD_MAX = "max"

# Cross-platform selectors; `__$labels__` is replaced by the Task 5 handler.
ZOMBIE_METRIC_SPECS: dict[str, dict[str, Any]] = {
    "cpu": {
        "query": (
            '(100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", __$labels__})'
            ' or host_cpu_usage_percent_gauge{instance_type="os", __$labels__}'
            ' or cpu_usage_total_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}'
        ),
        "fold": FOLD_IDENTITY,
        "windows": ("avg", "max"),
    },
    "mem": {
        "query": (
            'mem_used_percent{instance_type="os", __$labels__}'
            ' or host_mem_used_percent_gauge{instance_type="os", __$labels__}'
            ' or mem_used_percent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}'
        ),
        "fold": FOLD_IDENTITY,
        "windows": ("avg", "max"),
    },
    "packets": {
        "query": (
            'rate(net_packets_recv{instance_type="os", __$labels__}[5m])'
            ' or rate(net_packets_recv_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[5m])'
        ),
        "fold": FOLD_SUM,
        "windows": ("avg", "max"),
    },
    "io": {
        "query": (
            'diskio_io_util{instance_type="os", __$labels__}'
            ' or diskio_io_util_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}'
        ),
        "fold": FOLD_MAX,
        "windows": ("max",),
    },
}

# (min_key, max_key, row_field)
_THRESHOLD_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("login_min", "login_max", "login_count"),
    ("packets_recv_max_min", "packets_recv_max_max", "packets_recv_max"),
    ("packets_recv_avg_min", "packets_recv_avg_max", "packets_recv_avg"),
    ("cpu_avg_min", "cpu_avg_max", "cpu_avg"),
    ("cpu_max_min", "cpu_max_max", "cpu_max"),
    ("mem_avg_min", "mem_avg_max", "mem_avg"),
    ("mem_max_min", "mem_max_max", "mem_max"),
    ("io_max_min", "io_max_max", "io_max"),
)

DISPLAY_DECIMAL_FIELDS = (
    "packets_recv_max",
    "packets_recv_avg",
    "cpu_avg",
    "cpu_max",
    "mem_avg",
    "mem_max",
    "io_max",
)


def range_window(start_ts: float, end_ts: float) -> str:
    """Window duration for avg_over_time / max_over_time; delegates to metric_series."""
    return window_selector(start_ts, end_ts)


def wrap_max_over_time(query: str, window: str) -> str:
    return f"max_over_time(({query})[{window}])"


def _parse_bound(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValueError("threshold bound must be an integer")
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("threshold bound must be an integer")
        return int(value)
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError("threshold bound must be an integer") from exc


def parse_threshold(raw: Mapping[str, Any] | None) -> dict[str, int]:
    source = {} if raw is None else raw
    if not isinstance(source, Mapping):
        raise TypeError("threshold must be a mapping")
    parsed = dict(DEFAULT_THRESHOLDS)
    for key, default in DEFAULT_THRESHOLDS.items():
        if key not in source:
            continue
        parsed[key] = _parse_bound(source.get(key), default)
    return parsed


def _as_finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _bound_is_set(lo: int, hi: int) -> bool:
    return lo != UNBOUNDED or hi != UNBOUNDED


def _in_closed_interval(value: float, lo: int, hi: int) -> bool:
    if lo != UNBOUNDED and value < lo:
        return False
    if hi != UNBOUNDED and value > hi:
        return False
    return True


def _field_passes(row: Mapping[str, Any], field: str, lo: int, hi: int, *, skip_none: bool) -> bool:
    if skip_none:
        return True
    value = row.get(field)
    if value is None:
        return not _bound_is_set(lo, hi)
    number = _as_finite_number(value)
    if number is None:
        return False
    return _in_closed_interval(number, lo, hi)


def row_passes(row: Mapping[str, Any], t: Mapping[str, int]) -> bool:
    skip_login = str(row.get("login_status") or "") == LOGIN_STATUS_UNCOLLECTED
    for min_key, max_key, field in _THRESHOLD_FIELDS:
        lo = int(t.get(min_key, UNBOUNDED))
        hi = int(t.get(max_key, UNBOUNDED))
        skip_none = skip_login and field == "login_count"
        if not _field_passes(row, field, lo, hi, skip_none=skip_none):
            return False
    return True


def apply_thresholds(rows: list[Mapping[str, Any]], t: Mapping[str, int]) -> list[Mapping[str, Any]]:
    return [row for row in rows if row_passes(row, t)]


def _round_display_number(value: Any) -> float | None:
    number = _as_finite_number(value)
    if number is None:
        return None
    quantized = Decimal(str(number)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(quantized)


def round_display_metrics(row: Mapping[str, Any]) -> dict[str, Any]:
    """出表数字保留两位小数；登录次数仍是整数，阈值过滤仍用原始精度。"""
    formatted = dict(row)
    for field in DISPLAY_DECIMAL_FIELDS:
        if field in formatted:
            formatted[field] = _round_display_number(formatted.get(field))
    return formatted


def _series_instance_id(item: Mapping[str, Any]) -> str:
    for key in ("instance_id", "monitor_id"):
        raw = item.get(key)
        if raw not in (None, ""):
            return str(raw)
    return ""


def fold_io_max(series: list[Mapping[str, Any]] | None) -> dict[str, float]:
    folded: dict[str, float] = {}
    if not series:
        return folded
    for item in series:
        if not isinstance(item, Mapping):
            continue
        instance_id = _series_instance_id(item)
        if not instance_id:
            continue
        number = _as_finite_number(item.get("value"))
        if number is None:
            continue
        current = folded.get(instance_id)
        if current is None or number > current:
            folded[instance_id] = number
    return folded


def validate_inst_uuids(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise TypeError("inst_uuids 必须是列表")
    unique: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    if len(unique) > MAX_HOSTS:
        raise ValueError("一次最多查询 100 台主机")
    return unique
