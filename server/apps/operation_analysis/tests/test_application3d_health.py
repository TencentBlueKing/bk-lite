from types import SimpleNamespace

from apps.operation_analysis.services.application3d.health import aggregate_application_health, unavailable_health
from apps.operation_analysis.services.application3d.notifications import summarize_notification
from apps.operation_analysis.services.application3d.presenters import present_alarm_list_item
from apps.operation_analysis.services.application3d.severity import severity_from_monitor_level


def _counts(**overrides):
    counts = {"critical": 0, "error": 0, "warning": 0, "info": 0}
    counts.update(overrides)
    return counts


def _assert_severity_sum(health):
    assert sum(health["severityCounts"].values()) == health["activeAlarmCount"]


def test_severity_from_monitor_level_maps_known_levels():
    critical = severity_from_monitor_level("critical")
    assert critical == {
        "id": "critical",
        "label": "严重",
        "rank": 400,
        "color": "critical",
    }
    assert severity_from_monitor_level("WARNING")["id"] == "warning"
    assert severity_from_monitor_level("info")["id"] == "info"
    assert severity_from_monitor_level("no_data") is None
    assert severity_from_monitor_level(None)["id"] == "warning"
    assert severity_from_monitor_level("")["id"] == "warning"
    assert severity_from_monitor_level("   ")["id"] == "warning"


def test_aggregate_health_zero_alerts_is_normal():
    health = aggregate_application_health([])
    assert health["state"] == "normal"
    assert health["reason"] == "no_active_alarm"
    assert health["activeAlarmCount"] == 0
    assert health["highestSeverity"]["id"] == "normal"
    assert health["severityCounts"] == _counts()
    _assert_severity_sum(health)


def test_aggregate_health_only_no_data_critical_is_alarming():
    health = aggregate_application_health([{"alert_type": "no_data", "level": "critical"}])
    assert health["state"] == "alarming"
    assert health["reason"] == "active_alarm"
    assert health["activeAlarmCount"] == 1
    assert health["noDataAlarmCount"] == 1
    assert health["highestSeverity"]["id"] == "critical"
    assert health["severityCounts"] == _counts(critical=1)
    _assert_severity_sum(health)


def test_aggregate_health_only_no_data_error_is_alarming():
    health = aggregate_application_health([{"alert_type": "no_data", "level": "error"}])
    assert health["state"] == "alarming"
    assert health["highestSeverity"]["id"] == "error"
    assert health["severityCounts"] == _counts(error=1)
    _assert_severity_sum(health)


def test_aggregate_health_only_no_data_warning_is_alarming():
    health = aggregate_application_health([{"alert_type": "no_data", "level": "warning"}])
    assert health["state"] == "alarming"
    assert health["highestSeverity"]["id"] == "warning"
    assert health["severityCounts"] == _counts(warning=1)
    _assert_severity_sum(health)


def test_aggregate_health_no_data_critical_plus_ordinary_warning():
    health = aggregate_application_health(
        [
            {"alert_type": "no_data", "level": "critical"},
            {"alert_type": "alert", "level": "warning"},
        ]
    )
    assert health["state"] == "alarming"
    assert health["activeAlarmCount"] == 2
    assert health["noDataAlarmCount"] == 1
    assert health["highestSeverity"]["id"] == "critical"
    assert health["severityCounts"] == _counts(critical=1, warning=1)
    _assert_severity_sum(health)


def test_aggregate_health_no_data_warning_plus_ordinary_critical():
    health = aggregate_application_health(
        [
            {"alert_type": "no_data", "level": "warning"},
            {"alert_type": "alert", "level": "critical"},
        ]
    )
    assert health["highestSeverity"]["id"] == "critical"
    assert health["severityCounts"] == _counts(critical=1, warning=1)
    _assert_severity_sum(health)


def test_aggregate_health_multiple_no_data_severities():
    health = aggregate_application_health(
        [
            {"alert_type": "no_data", "level": "critical"},
            {"alert_type": "no_data", "level": "warning"},
        ]
    )
    assert health["activeAlarmCount"] == 2
    assert health["noDataAlarmCount"] == 2
    assert health["highestSeverity"]["id"] == "critical"
    assert health["severityCounts"] == _counts(critical=1, warning=1)
    _assert_severity_sum(health)


def test_aggregate_health_empty_level_is_treated_as_warning():
    health = aggregate_application_health([{"alert_type": "no_data", "level": ""}])
    assert health["state"] == "alarming"
    assert health["reason"] == "active_alarm"
    assert health["activeAlarmCount"] == 1
    assert health["noDataAlarmCount"] == 1
    assert health["highestSeverity"]["id"] == "warning"
    assert health["severityCounts"] == _counts(warning=1)
    _assert_severity_sum(health)


def test_aggregate_health_ordinary_info_is_alarming_compatibility():
    health = aggregate_application_health([{"alert_type": "alert", "level": "info"}])
    assert health["state"] == "alarming"
    assert health["reason"] == "active_alarm"
    assert health["severityCounts"] == _counts(info=1)
    assert health["highestSeverity"]["id"] == "info"
    _assert_severity_sum(health)


def test_aggregate_health_no_data_info_is_alarming_compatibility():
    health = aggregate_application_health([{"alert_type": "no_data", "level": "info"}])
    assert health["state"] == "alarming"
    assert health["noDataAlarmCount"] == 1
    assert health["severityCounts"] == _counts(info=1)
    assert health["highestSeverity"]["id"] == "info"
    _assert_severity_sum(health)


def test_aggregate_health_ordinary_plus_no_data_uses_max_level():
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
    assert health["highestSeverity"]["id"] == "critical"
    assert health["severityCounts"] == _counts(critical=1, error=1, warning=1)
    _assert_severity_sum(health)


def test_unavailable_health_uses_null_counts():
    health = unavailable_health()
    assert health["state"] == "unknown"
    assert health["reason"] == "unavailable"
    assert health["activeAlarmCount"] is None
    assert health["severityCounts"] is None
    assert health["highestSeverity"] is None


def test_no_data_critical_aligns_with_monitor_max_level():
    from apps.monitor.nats.monitor import _max_monitor_alert_level

    # Monitor max_level / notification mapping uses MonitorAlert.level, not alert_type.
    assert _max_monitor_alert_level(["critical"]) == "critical"
    assert _max_monitor_alert_level(["warning", "critical"]) == "critical"

    only_no_data = aggregate_application_health([{"alert_type": "no_data", "level": "critical"}])
    assert only_no_data["state"] == "alarming"
    assert only_no_data["highestSeverity"]["id"] == _max_monitor_alert_level(["critical"])

    mixed = aggregate_application_health(
        [
            {"alert_type": "no_data", "level": "warning"},
            {"alert_type": "alert", "level": "critical"},
        ]
    )
    assert mixed["highestSeverity"]["id"] == _max_monitor_alert_level(["warning", "critical"])


def test_no_data_alarm_list_item_keeps_severity():
    alert = SimpleNamespace(
        id=7,
        content="主机无数据",
        alert_type="no_data",
        level="critical",
        start_event_time=None,
        end_event_time=None,
    )
    item = present_alarm_list_item(
        alert,
        host={"inst_uuid": "host-1", "inst_name": "host-1"},
        policy=SimpleNamespace(alert_name="cpu", name="CPU"),
    )
    assert item["isNoData"] is True
    assert item["severity"]["id"] == "critical"


def test_empty_level_alarm_list_item_severity_is_warning():
    alert = SimpleNamespace(
        id=8,
        content="空级别无数据",
        alert_type="no_data",
        level="",
        start_event_time=None,
        end_event_time=None,
    )
    item = present_alarm_list_item(
        alert,
        host={"inst_uuid": "host-1", "inst_name": "host-1"},
        policy=SimpleNamespace(alert_name="cpu", name="CPU"),
    )
    assert item["isNoData"] is True
    assert item["severity"]["id"] == "warning"
    assert item["severity"]["color"] == "warning"


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
