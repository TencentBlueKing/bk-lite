from typing import Any

DEFAULT_MAX_SERIES = 20
HARD_MAX_SERIES = 50


def clamp_max_series(value) -> int:
    """Default 20 if missing/invalid; clamp to [1, 50]."""
    if value is None:
        return DEFAULT_MAX_SERIES
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_SERIES
    if n < 1:
        return 1
    if n > HARD_MAX_SERIES:
        return HARD_MAX_SERIES
    return n


def format_series_legend(metric: dict) -> str:
    if not metric:
        return "series"
    name = metric.get("__name__")
    labels = {k: v for k, v in metric.items() if k != "__name__"}
    if not labels:
        return name if name else "series"
    label_parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    if name:
        return f"{name}{{{label_parts}}}"
    return f"{{{label_parts}}}"


def _truncate_results(result: list, max_series: int) -> tuple[list, list[str] | None]:
    clamped = clamp_max_series(max_series)
    total = len(result)
    if total <= clamped:
        return result, None
    return result[:clamped], [f"结果共 {total} 条序列，已截断为 {clamped} 条"]


def _transform_values(values: list) -> list[dict]:
    return [{"name": ts, "value": v} for ts, v in values]


def transform_range_result(
    data: dict, max_series: int = DEFAULT_MAX_SERIES
) -> tuple[Any, list[str] | None]:
    result = data.get("result", [])
    if not result:
        return [], None

    truncated, warnings = _truncate_results(result, max_series)

    if len(truncated) == 1:
        series = truncated[0]
        return _transform_values(series.get("values", [])), warnings

    output = {}
    for series in truncated:
        legend = format_series_legend(series.get("metric", {}))
        output[legend] = _transform_values(series.get("values", []))
    return output, warnings


def transform_instant_result(
    data: dict, max_series: int = DEFAULT_MAX_SERIES
) -> tuple[Any, list[str] | None]:
    result = data.get("result", [])
    if not result:
        return [], None

    truncated, warnings = _truncate_results(result, max_series)

    rows = []
    for series in truncated:
        legend = format_series_legend(series.get("metric", {}))
        value_pair = series.get("value", [])
        v = value_pair[1] if len(value_pair) >= 2 else None
        rows.append({"name": legend, "value": v})
    return rows, warnings
