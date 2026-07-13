import re

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


PERIOD_PATTERN = re.compile(r"^(\d+)([mhd])$")
GROUP_AGGREGATION_ALGORITHMS = {"sum", "avg", "max", "min", "count"}
WINDOW_AGGREGATION_ALGORITHMS = {
    "max_over_time",
    "min_over_time",
    "avg_over_time",
    "sum_over_time",
    "count_over_time",
    "last_over_time",
}
LEGACY_ALGORITHM_MAPPING = {
    "avg": ("avg", "avg_over_time"),
    "avg_over_time": ("avg", "avg_over_time"),
    "max": ("max", "max_over_time"),
    "max_over_time": ("max", "max_over_time"),
    "min": ("min", "min_over_time"),
    "min_over_time": ("min", "min_over_time"),
    "sum": ("sum", "sum_over_time"),
    "sum_over_time": ("sum", "sum_over_time"),
    "count": ("count", "last_over_time"),
    "count_over_time": ("count", "count_over_time"),
    "last_over_time": ("avg", "last_over_time"),
}


def period_to_seconds(period):
    """周期转换为秒"""
    if not period:
        raise BaseAppException("policy period is empty")
    if period["type"] == "min":
        return period["value"] * 60
    elif period["type"] == "hour":
        return period["value"] * 3600
    elif period["type"] == "day":
        return period["value"] * 86400
    else:
        raise BaseAppException(f"invalid period type: {period['type']}")


def period_step(period):
    """按汇聚周期自动生成 30 个采样点对应的子查询 step。"""
    matched = PERIOD_PATTERN.fullmatch(str(period or ""))
    if not matched:
        raise BaseAppException(f"invalid period: {period}")

    value = int(matched.group(1))
    unit = matched.group(2)
    period_seconds = value * {"m": 60, "h": 3600, "d": 86400}[unit]
    seconds = max(1, period_seconds // 30)
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def normalize_policy_algorithms(algorithm, group_algorithm=None):
    if group_algorithm:
        if group_algorithm not in GROUP_AGGREGATION_ALGORITHMS:
            raise BaseAppException(f"invalid group algorithm method: {group_algorithm}")
        if algorithm not in WINDOW_AGGREGATION_ALGORITHMS:
            raise BaseAppException(f"invalid algorithm method: {algorithm}")
        return group_algorithm, algorithm

    if algorithm not in LEGACY_ALGORITHM_MAPPING:
        raise BaseAppException(f"invalid algorithm method: {algorithm}")
    return LEGACY_ALGORITHM_MAPPING[algorithm]


def _sum(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("sum", metric_query, step, group_by, group_algorithm)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _avg(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("avg", metric_query, step, group_by, group_algorithm)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _max(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("max", metric_query, step, group_by, group_algorithm)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _min(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("min", metric_query, step, group_by, group_algorithm)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _count(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("count", metric_query, step, group_by, group_algorithm)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


# def last_over_time(metric_query, start, end, step, group_by):
#     query = f"any(last_over_time({metric_query})) by ({group_by})"
#     metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
#     return metrics


def build_policy_query(algorithm, metric_query, step, group_by, group_algorithm=None):
    group_algorithm, algorithm = normalize_policy_algorithms(algorithm, group_algorithm)
    if not group_by:
        raise BaseAppException("group_by is required")
    return f"{algorithm}(({group_algorithm}({metric_query}) by ({group_by}))[{step}:{period_step(step)}])"


def build_formula_policy_query(algorithm, metric_query, step):
    _, algorithm = normalize_policy_algorithms(algorithm)
    return f"{algorithm}(({metric_query})[{step}:{period_step(step)}])"


def query_formula_policy_metrics(algorithm, metric_query, start, end, step):
    query = build_formula_policy_query(algorithm, metric_query, step)
    return VictoriaMetricsAPI().query_range(query, start, end, step)


def last_over_time(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("last_over_time", metric_query, step, group_by, group_algorithm)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def max_over_time(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("max_over_time", metric_query, step, group_by, group_algorithm)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def min_over_time(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("min_over_time", metric_query, step, group_by, group_algorithm)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def avg_over_time(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("avg_over_time", metric_query, step, group_by, group_algorithm)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def sum_over_time(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("sum_over_time", metric_query, step, group_by, group_algorithm)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def count_over_time(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("count_over_time", metric_query, step, group_by, group_algorithm)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


METHOD = {
    "sum": _sum,
    "avg": _avg,
    "max": _max,
    "min": _min,
    "count": _count,
    "max_over_time": max_over_time,
    "min_over_time": min_over_time,
    "avg_over_time": avg_over_time,
    "sum_over_time": sum_over_time,
    "count_over_time": count_over_time,
    "last_over_time": last_over_time,
}
