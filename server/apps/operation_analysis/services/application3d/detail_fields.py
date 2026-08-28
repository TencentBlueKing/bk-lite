from __future__ import annotations

from typing import Any

from apps.operation_analysis.services.application3d.severity import severity_from_monitor_level

_THRESHOLD_LEVELS = frozenset({"critical", "error", "warning", "info"})


def present_policy_thresholds(policy: Any) -> list[dict[str, Any]]:
    """
    Normalize MonitorPolicy.threshold into UI-oriented MetricThreshold rows.

    Preserves all valid entries in policy order (same list Monitor chart consumes).
    Does not invent thresholds or re-evaluate alert conditions.
    """
    raw = getattr(policy, "threshold", None) if policy is not None else None
    if not isinstance(raw, list):
        return []

    presented: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if numeric != numeric:  # NaN
            continue

        level_raw = str(item.get("level") or "").strip().lower()
        if level_raw not in _THRESHOLD_LEVELS:
            continue
        severity = severity_from_monitor_level(level_raw)
        label = str(severity["label"]) if severity else level_raw
        operator = item.get("method")
        presented.append(
            {
                "level": level_raw,
                "value": numeric,
                "operator": str(operator) if operator not in (None, "") else None,
                "label": label,
            }
        )
    return presented


def present_alert_dimensions(dimensions: Any) -> list[dict[str, str]]:
    """Convert MonitorAlert.dimensions into DisplayDimension rows; empty → []."""
    if not isinstance(dimensions, dict) or not dimensions:
        return []
    items: list[dict[str, str]] = []
    for key in sorted(str(k) for k in dimensions.keys()):
        raw = dimensions.get(key)
        if raw is None:
            continue
        if isinstance(raw, str) and not raw.strip():
            continue
        if isinstance(raw, (list, dict)) and not raw:
            continue
        items.append(
            {
                "key": key,
                "label": key,
                "displayValue": str(raw),
            }
        )
    return items
