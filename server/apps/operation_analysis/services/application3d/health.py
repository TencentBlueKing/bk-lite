from __future__ import annotations

from typing import Any, Iterable

from apps.operation_analysis.services.application3d.severity import empty_severity_counts, normal_severity, severity_from_monitor_level


def _is_no_data(alert: dict[str, Any]) -> bool:
    return str(alert.get("alert_type") or "").lower() == "no_data"


def aggregate_application_health(alerts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """
    Aggregate ScopedActiveAlerts into Wall/Detail health fields.

    Callers must only pass a complete, permission-scoped active alert collection.
    Incomplete mapping/permission paths must not call this — return unavailable instead.
    """
    severity_counts = empty_severity_counts()
    no_data_count = 0
    ordinary_count = 0
    highest: dict | None = None

    for alert in alerts:
        count = int(alert.get("count") or 1)
        if count <= 0:
            continue
        if _is_no_data(alert):
            no_data_count += count
            continue
        severity = severity_from_monitor_level(alert.get("level"))
        if severity is None:
            continue
        ordinary_count += count
        severity_id = severity["id"]
        if severity_id in severity_counts:
            severity_counts[severity_id] += count
        if highest is None or severity["rank"] > highest["rank"]:
            highest = severity

    active_total = ordinary_count + no_data_count

    if ordinary_count >= 1:
        return {
            "state": "alarming",
            "reason": "active_alarm",
            "activeAlarmCount": active_total,
            "severityCounts": severity_counts,
            "noDataAlarmCount": no_data_count,
            "highestSeverity": highest,
            "stale": False,
        }

    if no_data_count >= 1:
        return {
            "state": "unknown",
            "reason": "no_data_alarm",
            "activeAlarmCount": active_total,
            "severityCounts": severity_counts,
            "noDataAlarmCount": no_data_count,
            "highestSeverity": None,
            "stale": False,
        }

    return {
        "state": "normal",
        "reason": "no_active_alarm",
        "activeAlarmCount": 0,
        "severityCounts": severity_counts,
        "noDataAlarmCount": 0,
        "highestSeverity": normal_severity(),
        "stale": False,
    }


def unavailable_health() -> dict[str, Any]:
    return {
        "state": "unknown",
        "reason": "unavailable",
        "activeAlarmCount": None,
        "severityCounts": None,
        "noDataAlarmCount": None,
        "highestSeverity": None,
        "stale": False,
    }
