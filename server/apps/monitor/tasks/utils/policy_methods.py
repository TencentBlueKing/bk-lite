import math
import re
from dataclasses import dataclass

from apps.core.exceptions.base_app_exception import (
    BaseAppException,
    ValidationAppException,
)
from apps.monitor.utils.unit_converter import UnitConverter
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


PERIOD_PATTERN = re.compile(r"^(\d+)([mhd])$")
RATE_FUNCTION_RE = re.compile(r"\b(?:rate|irate|increase)\s*\(", re.IGNORECASE)

_DATA_BYTE_UNITS = (
    "bytes",
    "kibibytes",
    "mebibytes",
    "gibibytes",
    "tebibytes",
    "pebibytes",
)
_DATA_BYTE_RATE_UNITS = (
    "byteps",
    "kibyteps",
    "mibyteps",
    "gibyteps",
    "tibyteps",
    "pibyteps",
)
_DATA_BIT_UNITS = (
    "bits",
    "kilobits",
    "megabits",
    "gigabits",
    "terabits",
    "petabits",
)
_DATA_BIT_RATE_UNITS = (
    "bitps",
    "kbitps",
    "mbitps",
    "gbitps",
    "tbitps",
    "pbitps",
)
QUANTITY_TO_RATE_UNIT = {
    **dict(zip(_DATA_BYTE_UNITS, _DATA_BYTE_RATE_UNITS)),
    **dict(zip(_DATA_BIT_UNITS, _DATA_BIT_RATE_UNITS)),
    "counts": "cps",
    "count": "cps",
}
ALREADY_PER_SECOND_UNITS = (
    set(_DATA_BYTE_RATE_UNITS)
    | set(_DATA_BIT_RATE_UNITS)
    | {"cps", "msps", "hertz", "kilohertz", "megahertz"}
)

GROUP_AGGREGATION_ALGORITHMS = {"sum", "avg", "max", "min", "count"}
LEGACY_WINDOW_AGGREGATION_ALGORITHMS = {
    "max_over_time",
    "min_over_time",
    "avg_over_time",
    "sum_over_time",
    "count_over_time",
    "last_over_time",
}
QUANTILE_ALGORITHMS = {
    "p90_over_time": "0.90",
    "p95_over_time": "0.95",
    "p99_over_time": "0.99",
}
STDDEV_ALGORITHM = "stddev_over_time"
COUNT_IF_ALGORITHM = "count_if_over_time"
WINDOW_AGGREGATION_ALGORITHMS = (
    LEGACY_WINDOW_AGGREGATION_ALGORITHMS | set(QUANTILE_ALGORITHMS) | {STDDEV_ALGORITHM}
)
PER_SERIES_ALGORITHMS = {"rate", "changes", "deriv"}
NEW_ALGORITHMS = set(QUANTILE_ALGORITHMS) | {STDDEV_ALGORITHM, COUNT_IF_ALGORITHM} | PER_SERIES_ALGORITHMS
POLICY_ALGORITHMS = WINDOW_AGGREGATION_ALGORITHMS | {COUNT_IF_ALGORITHM} | PER_SERIES_ALGORITHMS
PREDICATE_TO_PROMQL = {
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<=",
    "=": "==",
    "!=": "!=",
}
ALLOWED_FORECAST_LOOKBACK = {("hour", 1), ("hour", 4), ("hour", 24)}
LEVEL_ALGORITHMS = {
    "avg",
    "max",
    "min",
    "last",
    "avg_over_time",
    "max_over_time",
    "min_over_time",
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
    "p90_over_time": ("avg", "p90_over_time"),
    "p95_over_time": ("avg", "p95_over_time"),
    "p99_over_time": ("avg", "p99_over_time"),
    "stddev_over_time": ("avg", "stddev_over_time"),
}

COMPARE_MODE_ABSOLUTE = "absolute"
COMPARE_MODE_PREVIOUS_WINDOW = "previous_window"
COMPARE_MODE_OFFSET_1H = "offset_1h"
COMPARE_MODE_OFFSET_24H = "offset_24h"
COMPARE_MODE_OFFSET_HOURS = "offset_hours"
COMPARE_MODE_OFFSET_DAYS = "offset_days"
COMPARE_MODE_BASELINE_DAYS = "baseline_days"
COMPARE_MODE_OFFSET_7D = "offset_7d"
COMPARE_MODE_OFFSET_30D = "offset_30d"
COMPARE_MODE_BASELINE_WEEKS = "baseline_weeks"
COMPARE_MODE_BASELINE_4W = "baseline_4w"
MAX_COMPARE_OFFSET_HOURS = 8760
MAX_COMPARE_OFFSET_DAYS = 365
MAX_COMPARE_BASELINE_WEEKS = 52
COMPARE_MODE_TIMELEFT = "timeleft"

COMPARE_MODES = {
    COMPARE_MODE_ABSOLUTE,
    COMPARE_MODE_PREVIOUS_WINDOW,
    COMPARE_MODE_OFFSET_1H,
    COMPARE_MODE_OFFSET_24H,
    COMPARE_MODE_OFFSET_HOURS,
    COMPARE_MODE_OFFSET_DAYS,
    COMPARE_MODE_BASELINE_DAYS,
    COMPARE_MODE_OFFSET_7D,
    COMPARE_MODE_OFFSET_30D,
    COMPARE_MODE_BASELINE_WEEKS,
    COMPARE_MODE_BASELINE_4W,
    COMPARE_MODE_TIMELEFT,
}
COMPARE_VALUE_KINDS = {"", "delta", "percent", "ratio", "hours"}
COMPARE_VALUE_KINDS_BY_MODE = {
    COMPARE_MODE_ABSOLUTE: {""},
    COMPARE_MODE_PREVIOUS_WINDOW: {"delta", "percent"},
    COMPARE_MODE_OFFSET_1H: {"percent", "ratio"},
    COMPARE_MODE_OFFSET_24H: {"percent", "ratio"},
    COMPARE_MODE_OFFSET_HOURS: {"percent", "ratio"},
    COMPARE_MODE_OFFSET_DAYS: {"percent", "ratio"},
    COMPARE_MODE_BASELINE_DAYS: {"delta", "percent"},
    COMPARE_MODE_OFFSET_7D: {"percent", "ratio"},
    COMPARE_MODE_OFFSET_30D: {"percent", "ratio"},
    COMPARE_MODE_BASELINE_WEEKS: {"delta", "percent"},
    COMPARE_MODE_BASELINE_4W: {"delta", "percent"},
    COMPARE_MODE_TIMELEFT: {"hours"},
}
COMPARE_OFFSET_BY_MODE = {
    COMPARE_MODE_OFFSET_1H: "1h",
    COMPARE_MODE_OFFSET_24H: "24h",
    COMPARE_MODE_OFFSET_7D: "7d",
    COMPARE_MODE_OFFSET_30D: "30d",
}
COMPARE_OFFSET_SECONDS = {
    COMPARE_MODE_OFFSET_1H: 3600,
    COMPARE_MODE_OFFSET_24H: 86400,
    COMPARE_MODE_OFFSET_7D: 7 * 86400,
    COMPARE_MODE_OFFSET_30D: 30 * 86400,
}
HIGH_SIDE_METHODS = {">", ">="}
LOW_SIDE_METHODS = {"<", "<="}
COMPARE_SPAN_CONFLICT_MESSAGE = "对照窗不能等于汇聚周期"
SPAN_FIELD_LABELS = {
    "compare_offset_hours": "对照小时数",
    "compare_offset_days": "对照天数",
    "compare_baseline_weeks": "对照周数",
}


@dataclass(frozen=True)
class ResultUnit:
    unit: str
    conversion_enabled: bool


def _policy_get(policy_like, name, default=None):
    if isinstance(policy_like, dict):
        return policy_like.get(name, default)
    return getattr(policy_like, name, default)


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


def format_period(period, points=1):
    """把策略周期对象格式化为 MetricsQL 步长，如 5m / 1h / 1d。"""
    if not period:
        raise BaseAppException("policy period is empty")

    period_type = period["type"]
    period_value = int(period["value"])
    period_unit_map = {
        "min": "m",
        "hour": "h",
        "day": "d",
    }
    if period_type not in period_unit_map:
        raise BaseAppException(f"invalid period type: {period_type}")
    del points
    return f"{period_value}{period_unit_map[period_type]}"


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
    # 短名 avg/max/min/sum/count 仍走历史映射；模型默认 group_algorithm=avg
    # 不得把它们误判成「已是 over_time + 显式分组」。
    if algorithm in LEGACY_ALGORITHM_MAPPING and algorithm not in WINDOW_AGGREGATION_ALGORITHMS:
        return LEGACY_ALGORITHM_MAPPING[algorithm]
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


def _format_promql_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError) as err:
        raise BaseAppException("invalid numeric value") from err
    if not math.isfinite(number):
        raise BaseAppException("invalid numeric value")
    if number.is_integer():
        return str(int(number))
    return repr(number)


def _resolve_group_algorithm(policy_like):
    group_algorithm = _policy_get(policy_like, "group_algorithm")
    if group_algorithm:
        if group_algorithm not in GROUP_AGGREGATION_ALGORITHMS:
            raise BaseAppException(f"invalid group algorithm method: {group_algorithm}")
        return group_algorithm
    algorithm = _policy_get(policy_like, "algorithm")
    if algorithm in LEGACY_ALGORITHM_MAPPING:
        return LEGACY_ALGORITHM_MAPPING[algorithm][0]
    return "avg"


def _compile_per_series_query(policy_like, base_query, step, group_by):
    algorithm = _policy_get(policy_like, "algorithm")
    if algorithm not in PER_SERIES_ALGORITHMS:
        raise BaseAppException(f"invalid algorithm method: {algorithm}")
    if not group_by:
        raise BaseAppException("group_by is required")
    group_algorithm = _resolve_group_algorithm(policy_like)
    return f"{group_algorithm}({algorithm}({base_query}[{step}])) by ({group_by})"


def _compile_count_if_query(policy_like, base_query, step, group_by, is_formula):
    predicate = _policy_get(policy_like, "count_predicate") or {}
    method = predicate.get("method")
    if method not in PREDICATE_TO_PROMQL:
        raise BaseAppException("count_predicate.method is required")
    op = PREDICATE_TO_PROMQL[method]
    value = _format_promql_number(predicate.get("value"))
    inner_step = period_step(step)
    if is_formula:
        compared = f"(({base_query}) {op} bool {value})"
        return f"sum_over_time({compared}[{step}:{inner_step}])"
    if not group_by:
        raise BaseAppException("group_by is required")
    group_algorithm = _resolve_group_algorithm(policy_like)
    compared = f"(({group_algorithm}({base_query}) by ({group_by})) {op} bool {value})"
    return f"sum_over_time({compared}[{step}:{inner_step}])"


def _compile_last_over_time_existence(policy_like, base_query, step, group_by):
    query_condition = _policy_get(policy_like, "query_condition") or {}
    if query_condition.get("type") == "formula":
        return f"last_over_time(({base_query})[{step}:{period_step(step)}])"
    if not group_by:
        raise BaseAppException("group_by is required")
    group_algorithm = _resolve_group_algorithm(policy_like)
    return (
        f"last_over_time(({group_algorithm}({base_query}) by ({group_by}))"
        f"[{step}:{period_step(step)}])"
    )


def _format_forecast_lookback(policy_like):
    lookback = _policy_get(policy_like, "forecast_lookback") or {}
    if not lookback:
        return "1h"
    if not isinstance(lookback, dict):
        raise BaseAppException("unsupported forecast_lookback")
    lookback_type = lookback.get("type")
    try:
        lookback_value = int(lookback.get("value"))
    except (TypeError, ValueError) as err:
        raise BaseAppException("unsupported forecast_lookback") from err
    if (lookback_type, lookback_value) not in ALLOWED_FORECAST_LOOKBACK:
        raise BaseAppException("unsupported forecast_lookback")
    return f"{lookback_value}h"


def _forecast_target_in_metric_unit(policy_like, target):
    """容量线按用户所选单位保存，查询里要和指标原始序列同一量纲。"""
    source_unit = str(_policy_get(policy_like, "forecast_target_unit") or "").strip()
    metric_unit = str(_policy_get(policy_like, "metric_unit") or "").strip()
    if not source_unit or source_unit == metric_unit:
        return target
    if not metric_unit or not UnitConverter.is_convertible(source_unit, metric_unit):
        raise BaseAppException("forecast_target_unit is not convertible to metric_unit")
    converted = UnitConverter.convert_values([float(target)], source_unit, metric_unit)
    return converted[0]


def compile_timeleft_query(policy_like, base_query, step, group_by=None):
    target = _policy_get(policy_like, "forecast_target")
    if target is None or target == "":
        raise BaseAppException("forecast_target is required")
    target = _forecast_target_in_metric_unit(policy_like, target)
    target_s = _format_promql_number(target)
    lookback = _format_forecast_lookback(policy_like)
    lookback_step = period_step(lookback)
    query_condition = _policy_get(policy_like, "query_condition") or {}
    if group_by is None:
        group_by = ",".join(_policy_get(policy_like, "group_by") or [])
    if query_condition.get("type") == "formula":
        water = f"last_over_time(({base_query})[{step}:{period_step(step)}])"
        slope_src = f"({base_query})[{lookback}:{lookback_step}]"
    else:
        if not group_by:
            raise BaseAppException("group_by is required")
        grouped = f"{_resolve_group_algorithm(policy_like)}({base_query}) by ({group_by})"
        water = f"last_over_time(({grouped})[{step}:{period_step(step)}])"
        slope_src = f"({grouped})[{lookback}:{lookback_step}]"
    return (
        f"clamp_min({target_s} - {water}, 0) / "
        f"clamp_min(deriv({slope_src}), 1e-9) / 3600"
    )


def _baseline_span_expr(query, count, stride_days):
    terms = " + ".join(
        f"{query} offset {index * stride_days}d" for index in range(1, count + 1)
    )
    return f"({terms}) / {count}"


def _baseline_days_expr(query, days):
    return _baseline_span_expr(query, days, 1)


def _baseline_weeks_expr(query, weeks):
    return _baseline_span_expr(query, weeks, 7)


def _baseline_4w_expr(query):
    return _baseline_weeks_expr(query, 4)


def span_value_message(label, raw, minimum, limit):
    """对照数量不合法时返回和保存校验相同的中文；合法则返回 None。"""
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < minimum:
        if minimum > 1:
            return f"{label}至少为 {minimum}"
        return f"{label}必须是正整数"
    if raw > limit:
        return f"{label}不能超过 {limit}"
    return None


def _positive_span(policy_like, field, maximum, minimum=1):
    raw = _policy_get(policy_like, field)
    label = SPAN_FIELD_LABELS.get(field, field)
    if isinstance(raw, bool):
        raise ValidationAppException(span_value_message(label, raw, minimum, maximum))
    try:
        value = int(raw)
    except (TypeError, ValueError) as err:
        raise ValidationAppException(
            span_value_message(label, None, minimum, maximum)
        ) from err
    message = span_value_message(label, value, minimum, maximum)
    if message:
        raise ValidationAppException(message)
    return value


def _window_range_selector(group_algorithm, metric_query, group_by, step):
    return f"({group_algorithm}({metric_query}) by ({group_by}))[{step}:{period_step(step)}]"


def build_policy_query(algorithm, metric_query, step, group_by, group_algorithm=None):
    group_algorithm, algorithm = normalize_policy_algorithms(algorithm, group_algorithm)
    if not group_by:
        raise BaseAppException("group_by is required")
    range_selector = _window_range_selector(group_algorithm, metric_query, group_by, step)
    phi = QUANTILE_ALGORITHMS.get(algorithm)
    if phi is not None:
        return f"quantile_over_time({phi}, ({range_selector}))"
    return f"{algorithm}({range_selector})"


def build_formula_policy_query(algorithm, metric_query, step):
    _, algorithm = normalize_policy_algorithms(algorithm)
    inner = f"({metric_query})[{step}:{period_step(step)}]"
    phi = QUANTILE_ALGORITHMS.get(algorithm)
    if phi is not None:
        return f"quantile_over_time({phi}, ({inner}))"
    return f"{algorithm}({inner})"


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


def _compile_window_query(policy_like, base_query, step, group_by):
    query_condition = _policy_get(policy_like, "query_condition") or {}
    algorithm = _policy_get(policy_like, "algorithm")
    group_algorithm = _policy_get(policy_like, "group_algorithm")
    is_formula = query_condition.get("type") == "formula"
    if algorithm in PER_SERIES_ALGORITHMS:
        if is_formula:
            raise BaseAppException("formula policy cannot use per-series algorithms")
        if algorithm == "rate" and base_query_contains_rate_function(base_query):
            raise BaseAppException("base query already contains rate/irate/increase")
        return _compile_per_series_query(policy_like, base_query, step, group_by)
    if algorithm == COUNT_IF_ALGORITHM:
        return _compile_count_if_query(policy_like, base_query, step, group_by, is_formula)
    if is_formula:
        return build_formula_policy_query(algorithm, base_query, step)
    return build_policy_query(algorithm, base_query, step, group_by, group_algorithm)


def _compare_offset(policy_like, step):
    mode = _policy_get(policy_like, "compare_mode") or COMPARE_MODE_ABSOLUTE
    if mode == COMPARE_MODE_PREVIOUS_WINDOW:
        return step
    if mode == COMPARE_MODE_OFFSET_HOURS:
        hours = _positive_span(policy_like, "compare_offset_hours", MAX_COMPARE_OFFSET_HOURS)
        return f"{hours}h"
    if mode == COMPARE_MODE_OFFSET_DAYS:
        days = _positive_span(policy_like, "compare_offset_days", MAX_COMPARE_OFFSET_DAYS)
        return f"{days}d"
    offset = COMPARE_OFFSET_BY_MODE.get(mode)
    if not offset:
        raise BaseAppException(f"unsupported compare_mode: {mode}")
    return offset


def apply_compare_mode(query, policy_like, step):
    mode = _policy_get(policy_like, "compare_mode") or COMPARE_MODE_ABSOLUTE
    kind = (_policy_get(policy_like, "compare_value_kind") or "").strip()
    if mode in ("", COMPARE_MODE_ABSOLUTE):
        return query
    if _policy_get(policy_like, "algorithm") == COUNT_IF_ALGORITHM:
        raise BaseAppException("count_if_over_time only allows absolute compare_mode")
    if mode == COMPARE_MODE_BASELINE_DAYS:
        days = _positive_span(
            policy_like,
            "compare_offset_days",
            MAX_COMPARE_OFFSET_DAYS,
            minimum=2,
        )
        baseline = _baseline_days_expr(query, days)
        if kind == "delta":
            return f"{query} - ({baseline})"
        if kind == "percent":
            return f"({query} - ({baseline})) / ({baseline}) * 100"
        raise BaseAppException(f"unsupported compare_value_kind: {kind}")
    if mode in (COMPARE_MODE_BASELINE_4W, COMPARE_MODE_BASELINE_WEEKS):
        weeks = (
            4
            if mode == COMPARE_MODE_BASELINE_4W
            else _positive_span(
                policy_like,
                "compare_baseline_weeks",
                MAX_COMPARE_BASELINE_WEEKS,
                minimum=2,
            )
        )
        baseline = _baseline_weeks_expr(query, weeks)
        if kind == "delta":
            return f"{query} - ({baseline})"
        if kind == "percent":
            return f"({query} - ({baseline})) / ({baseline}) * 100"
        raise BaseAppException(f"unsupported compare_value_kind: {kind}")
    if mode == COMPARE_MODE_TIMELEFT:
        raise BaseAppException("timeleft must use compile_timeleft_query")
    offset = _compare_offset(policy_like, step)
    baseline = f"{query} offset {offset}"
    if kind == "delta":
        return f"{query} - {baseline}"
    if kind == "percent":
        return f"({query} - {baseline}) / ({baseline}) * 100"
    if kind == "ratio":
        return f"{query} / ({baseline})"
    raise BaseAppException(f"unsupported compare_value_kind: {kind}")


def compile_window_query(policy_like, base_query, step, group_by=None):
    """当前窗聚合结果 q，不带比较基准。"""
    if group_by is None:
        group_by = ",".join(_policy_get(policy_like, "group_by") or [])
    return _compile_window_query(policy_like, base_query, step, group_by)


def compile_baseline_query(policy_like, base_query, step, group_by=None):
    """对照窗：offset / 近 4 周均值。absolute 时与当前窗相同。"""
    query = compile_window_query(policy_like, base_query, step, group_by)
    mode = _policy_get(policy_like, "compare_mode") or COMPARE_MODE_ABSOLUTE
    if mode in ("", COMPARE_MODE_ABSOLUTE, COMPARE_MODE_TIMELEFT):
        return query
    if mode == COMPARE_MODE_BASELINE_4W:
        return _baseline_4w_expr(query)
    if mode == COMPARE_MODE_BASELINE_DAYS:
        days = _positive_span(
            policy_like,
            "compare_offset_days",
            MAX_COMPARE_OFFSET_DAYS,
            minimum=2,
        )
        return _baseline_days_expr(query, days)
    if mode == COMPARE_MODE_BASELINE_WEEKS:
        weeks = _positive_span(
            policy_like,
            "compare_baseline_weeks",
            MAX_COMPARE_BASELINE_WEEKS,
            minimum=2,
        )
        return _baseline_weeks_expr(query, weeks)
    return f"{query} offset {_compare_offset(policy_like, step)}"


def compile_policy_query(policy_like, base_query, step, group_by=None):
    """比较查询：窗口聚合后再套比较基准。Trap 短路，不套对照。"""
    if group_by is None:
        group_by = ",".join(_policy_get(policy_like, "group_by") or [])
    if _policy_get(policy_like, "collect_type") == "trap":
        return _compile_window_query(policy_like, base_query, step, group_by)
    mode = _policy_get(policy_like, "compare_mode") or COMPARE_MODE_ABSOLUTE
    if mode == COMPARE_MODE_TIMELEFT:
        return compile_timeleft_query(policy_like, base_query, step, group_by)
    query = _compile_window_query(policy_like, base_query, step, group_by)
    return apply_compare_mode(query, policy_like, step)


def compile_existence_query(policy_like, base_query, step, group_by=None):
    """存在性查询：不套比较基准。

    窗口聚合类沿用策略原汇聚；逐序列类与 count_if 改用 last_over_time，
    避免单样本窗或零匹配窗被当成无数据。
    """
    if group_by is None:
        group_by = ",".join(_policy_get(policy_like, "group_by") or [])
    algorithm = _policy_get(policy_like, "algorithm")
    if algorithm in PER_SERIES_ALGORITHMS or algorithm == COUNT_IF_ALGORITHM:
        return _compile_last_over_time_existence(policy_like, base_query, step, group_by)
    return compile_window_query(policy_like, base_query, step, group_by)


def map_quantity_to_rate_unit(unit) -> str:
    """把存量指标量纲映射为「量纲 / 秒」；已是速率单位或无对应目录时原样返回。"""
    raw = (unit or "").strip()
    if not raw:
        return raw
    normalized = raw.lower()
    if normalized in ALREADY_PER_SECOND_UNITS:
        return normalized
    return QUANTITY_TO_RATE_UNIT.get(normalized, raw)


def resolve_result_unit(policy_like) -> ResultUnit:
    kind = (_policy_get(policy_like, "compare_value_kind") or "").strip()
    algorithm = (_policy_get(policy_like, "algorithm") or "").strip()
    metric_unit = _policy_get(policy_like, "metric_unit") or ""
    calculation_unit = _policy_get(policy_like, "calculation_unit") or metric_unit or ""

    if kind == "percent":
        return ResultUnit("percent", False)
    if kind == "ratio":
        return ResultUnit("", False)
    if kind == "hours":
        return ResultUnit("hour", False)
    if algorithm in {"changes", COUNT_IF_ALGORITHM}:
        return ResultUnit("count", False)
    if algorithm in {"rate", "deriv"}:
        return ResultUnit(map_quantity_to_rate_unit(metric_unit or calculation_unit), False)
    return ResultUnit(calculation_unit, True)


def base_query_contains_rate_function(base_query):
    return bool(RATE_FUNCTION_RE.search(base_query or ""))


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
