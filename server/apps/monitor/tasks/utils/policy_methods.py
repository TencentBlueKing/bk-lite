import re

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


SIMPLE_SELECTOR_PATTERN = re.compile(r"^(?:[a-zA-Z_:][a-zA-Z0-9_:]*|\{[^{}]*\})(?:\{[^{}]*\})?$")
NORMAL_AGGREGATION_ALGORITHMS = {"sum", "avg", "max", "min", "count"}
OVER_TIME_AGGREGATION_ALGORITHMS = {
    "max_over_time",
    "min_over_time",
    "avg_over_time",
    "sum_over_time",
    "last_over_time",
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


def _sum(metric_query, start, end, step, group_by):
    query = build_policy_query("sum", metric_query, step, group_by)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _avg(metric_query, start, end, step, group_by):
    query = build_policy_query("avg", metric_query, step, group_by)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _max(metric_query, start, end, step, group_by):
    query = build_policy_query("max", metric_query, step, group_by)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _min(metric_query, start, end, step, group_by):
    query = build_policy_query("min", metric_query, step, group_by)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def _count(metric_query, start, end, step, group_by):
    query = build_policy_query("count", metric_query, step, group_by)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


# def last_over_time(metric_query, start, end, step, group_by):
#     query = f"any(last_over_time({metric_query})) by ({group_by})"
#     metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
#     return metrics


def _supports_explicit_range_selector(metric_query: str) -> bool:
    query = (metric_query or "").strip()
    return bool(query) and bool(SIMPLE_SELECTOR_PATTERN.fullmatch(query))


def _format_over_time_query(function_name, metric_query, step, group_by):
    if _supports_explicit_range_selector(metric_query):
        metric_query = f"{metric_query}[{step}]"
    return f"any({function_name}({metric_query})) by ({group_by})"


def build_policy_query(algorithm, metric_query, step, group_by):
    if algorithm in NORMAL_AGGREGATION_ALGORITHMS:
        return f"{algorithm}({metric_query}) by ({group_by})"
    if algorithm in OVER_TIME_AGGREGATION_ALGORITHMS:
        return _format_over_time_query(algorithm, metric_query, step, group_by)
    raise BaseAppException(f"invalid algorithm method: {algorithm}")


def last_over_time(metric_query, start, end, step, group_by):
    # 仅对简单 selector（裸指标、label-only、metric{labels}）显式补 range selector。
    # 对复杂表达式保持原样，继续沿用 step + instant query 的兼容路径，避免在无法可靠
    # 重写 PromQL/MetricsQL 时引入新的语义漂移。
    if _supports_explicit_range_selector(metric_query):
        query = build_policy_query("last_over_time", metric_query, step, group_by)
        metrics = VictoriaMetricsAPI().query(query, None, end)
    else:
        query = build_policy_query("last_over_time", metric_query, step, group_by)
        metrics = VictoriaMetricsAPI().query(query, step, end)
    for data in metrics.get("data", {}).get("result", []):
        data["values"] = [data["value"]]
    return metrics


def max_over_time(metric_query, start, end, step, group_by):
    query = build_policy_query("max_over_time", metric_query, step, group_by)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def min_over_time(metric_query, start, end, step, group_by):
    query = build_policy_query("min_over_time", metric_query, step, group_by)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def avg_over_time(metric_query, start, end, step, group_by):
    query = build_policy_query("avg_over_time", metric_query, step, group_by)
    metrics = VictoriaMetricsAPI().query_range(query, start, end, step)
    return metrics


def sum_over_time(metric_query, start, end, step, group_by):
    query = build_policy_query("sum_over_time", metric_query, step, group_by)
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
    "last_over_time": last_over_time,
}
