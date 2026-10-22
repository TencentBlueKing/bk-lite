"""把完整时序收成趋势汇总行，避免把原始点交给大模型。"""

from __future__ import annotations

from typing import Any

MAX_TREND_ROWS = 50
# 每天变化低于这个幅度视为不增长，不报「即将超阈值」。
MIN_SLOPE_PER_DAY = 1e-4
_KEEP_LABELS = ("instance_id", "path", "device", "fstype")


def linear_slope_per_day(points: list[tuple[float, float]]) -> float | None:
    """最小二乘斜率，单位是每个自然日的变化量。点不足两个时返回 None。"""
    if len(points) < 2:
        return None
    origin = points[0][0]
    xs = [(ts - origin) / 86400 for ts, _value in points]
    ys = [value for _ts, value in points]
    count = len(xs)
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    variance = sum((item - mean_x) ** 2 for item in xs)
    if variance <= 0:
        return 0.0
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / variance


def _series_points(series: dict) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for pair in series.get("values") or []:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        try:
            points.append((float(pair[0]), float(pair[1])))
        except (TypeError, ValueError):
            continue
    points.sort(key=lambda item: item[0])
    return points


def _labels_of(series: dict) -> dict[str, str]:
    raw = series.get("metric") if isinstance(series.get("metric"), dict) else {}
    labels = {}
    for key in _KEEP_LABELS:
        value = raw.get(key)
        if value not in (None, ""):
            labels[key] = str(value)
    return labels


def summarize_trend_rows(
    series_list: list[dict],
    *,
    threshold: float,
    horizon_days: float,
) -> dict[str, Any]:
    """每条有效序列都返回当前值、斜率和到达阈值的天数。within_horizon 标记预测跨度内会到达阈值的序列。"""
    rows: list[dict[str, Any]] = []
    scanned = 0
    for series in series_list or []:
        if not isinstance(series, dict):
            continue
        points = _series_points(series)
        if len(points) < 2:
            continue
        scanned += 1
        slope = linear_slope_per_day(points)
        current = points[-1][1]
        if slope is None:
            continue
        if current >= threshold:
            days: float | None = 0.0
            within = True
        elif slope <= MIN_SLOPE_PER_DAY:
            days = None
            within = False
        else:
            days = (threshold - current) / slope
            within = 0 <= days <= horizon_days
        labels = _labels_of(series)
        rows.append(
            {
                "instance_id": labels.get("instance_id") or "",
                "labels": labels,
                "current": round(current, 2),
                "slope_per_day": round(slope, 4),
                "days_to_threshold": None if days is None else round(days, 2),
                "within_horizon": within,
            }
        )
    hit_count = sum(1 for row in rows if row["within_horizon"])
    rows.sort(
        key=lambda row: (
            0 if row["within_horizon"] else 1,
            row["days_to_threshold"] if row["days_to_threshold"] is not None else float("inf"),
            -row["current"],
            row["instance_id"],
            str(row["labels"]),
        )
    )
    returned_rows = rows[:MAX_TREND_ROWS]
    hits_in_returned = sum(1 for row in returned_rows if row["within_horizon"])
    omitted_hits = max(0, hit_count - hits_in_returned)
    return {
        "scanned_series": scanned,
        "hit_count": hit_count,
        "truncated": omitted_hits > 0,
        "omitted_count": omitted_hits,
        "threshold": threshold,
        "horizon_days": horizon_days,
        "rows": returned_rows,
    }
