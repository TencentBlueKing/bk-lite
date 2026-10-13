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
    """只保留预测跨度内会到达阈值的序列，并给出扫描量。"""
    hits: list[dict[str, Any]] = []
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
        days: float | None
        if current >= threshold:
            days = 0.0
            within = True
        elif slope <= MIN_SLOPE_PER_DAY:
            days = None
            within = False
        else:
            days = (threshold - current) / slope
            within = 0 <= days <= horizon_days
        if not within or days is None:
            continue
        labels = _labels_of(series)
        hits.append(
            {
                "instance_id": labels.get("instance_id") or "",
                "labels": labels,
                "current": round(current, 2),
                "slope_per_day": round(slope, 4),
                "days_to_threshold": round(days, 2),
                "within_horizon": True,
            }
        )
    hits.sort(key=lambda row: (row["days_to_threshold"], row["instance_id"], str(row["labels"])))
    truncated = len(hits) > MAX_TREND_ROWS
    return {
        "scanned_series": scanned,
        "hit_count": len(hits),
        "truncated": truncated,
        "omitted_count": max(0, len(hits) - MAX_TREND_ROWS),
        "threshold": threshold,
        "horizon_days": horizon_days,
        "rows": hits[:MAX_TREND_ROWS],
    }
