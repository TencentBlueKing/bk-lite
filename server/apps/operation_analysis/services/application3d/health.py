from __future__ import annotations

from typing import Any, Iterable

from apps.operation_analysis.services.application3d.severity import empty_severity_counts, normal_severity, severity_from_monitor_level


def _is_no_data(alert: dict[str, Any]) -> bool:
    return str(alert.get("alert_type") or "").lower() == "no_data"


def aggregate_application_health(alerts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """
    Aggregate ScopedActiveAlerts into Wall/Detail health fields.

    `alert_type` and `level` are orthogonal: no_data alerts still contribute
    their MonitorAlert.level to severityCounts / highestSeverity.
    Incomplete mapping/permission paths must not call this — return unavailable instead.
    """
    severity_counts = empty_severity_counts()
    no_data_count = 0
    active_total = 0
    highest: dict | None = None

    for alert in alerts:
        count = int(alert.get("count") or 1)
        if count <= 0:
            continue
        active_total += count
        if _is_no_data(alert):
            no_data_count += count
        severity = severity_from_monitor_level(alert.get("level"))
        if severity is None:
            # Non-empty unmapped level: count toward activeAlarmCount only.
            continue
        severity_id = severity["id"]
        if severity_id in severity_counts:
            severity_counts[severity_id] += count
        if highest is None or severity["rank"] > highest["rank"]:
            highest = severity

    if active_total >= 1:
        return {
            "state": "alarming",
            "reason": "active_alarm",
            "activeAlarmCount": active_total,
            "severityCounts": severity_counts,
            "noDataAlarmCount": no_data_count,
            "highestSeverity": highest,
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
