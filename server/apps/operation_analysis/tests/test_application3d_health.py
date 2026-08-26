from apps.operation_analysis.services.application3d.health import aggregate_application_health, unavailable_health
from apps.operation_analysis.services.application3d.notifications import summarize_notification
from apps.operation_analysis.services.application3d.severity import severity_from_monitor_level


def test_severity_from_monitor_level_maps_known_levels():
    critical = severity_from_monitor_level("critical")
    assert critical == {
        "id": "critical",
        "label": "致命",
        "rank": 400,
        "color": "critical",
    }
    assert severity_from_monitor_level("WARNING")["id"] == "warning"
    assert severity_from_monitor_level("no_data") is None
    assert severity_from_monitor_level(None) is None


def test_aggregate_health_zero_alerts_is_normal():
    health = aggregate_application_health([])
    assert health["state"] == "normal"
    assert health["reason"] == "no_active_alarm"
    assert health["activeAlarmCount"] == 0
    assert health["highestSeverity"]["id"] == "normal"
    assert health["severityCounts"] == {
        "critical": 0,
        "error": 0,
        "warning": 0,
        "info": 0,
    }


def test_aggregate_health_only_no_data_is_unknown():
    health = aggregate_application_health([{"alert_type": "no_data", "level": "warning"}])
    assert health["state"] == "unknown"
    assert health["reason"] == "no_data_alarm"
    assert health["activeAlarmCount"] == 1
    assert health["noDataAlarmCount"] == 1
    assert health["highestSeverity"] is None
    assert health["severityCounts"]["warning"] == 0


def test_aggregate_health_ordinary_plus_no_data_is_alarming():
    health = aggregate_application_health(
        [
            {"alert_type": "alert", "level": "warning"},
            {"alert_type": "no_data", "level": "critical"},
            {"alert_type": "alert", "level": "error"},
        ]
    )
    assert health["state"] == "alarming"
    assert health["reason"] == "active_alarm"
    assert health["activeAlarmCount"] == 3
    assert health["noDataAlarmCount"] == 1
    assert health["highestSeverity"]["id"] == "error"
    assert health["severityCounts"] == {
        "critical": 0,
        "error": 1,
        "warning": 1,
        "info": 0,
    }


def test_unavailable_health_uses_null_counts():
    health = unavailable_health()
    assert health["state"] == "unknown"
    assert health["reason"] == "unavailable"
    assert health["activeAlarmCount"] is None
    assert health["severityCounts"] is None


def test_notification_summary_not_configured():
    assert summarize_notification(policy_notice_configured=False, notice_logs=[{"success": True}]) == {
        "configured": False,
        "state": "not_configured",
    }


def test_notification_summary_ignores_alert_center_and_aggregates_delivery():
    assert summarize_notification(
        policy_notice_configured=True,
        notice_logs=[
            {"success": True, "is_alert_center": True},
            {"success": True, "channel_id": 1},
            {"success": False, "channel_id": 2},
        ],
    ) == {"configured": True, "state": "partially_delivered"}

    assert summarize_notification(policy_notice_configured=True, notice_logs=[]) == {
        "configured": True,
        "state": "pending",
    }
