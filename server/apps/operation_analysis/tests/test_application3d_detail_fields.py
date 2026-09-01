from types import SimpleNamespace

from apps.operation_analysis.services.application3d.detail_fields import present_alert_dimensions, present_policy_thresholds
from apps.operation_analysis.services.application3d.metric_fields import resolve_policy_metric_display_name
from apps.operation_analysis.services.application3d.presenters import alert_duration_seconds


def test_present_policy_thresholds_keeps_all_valid_rows_in_order():
    policy = SimpleNamespace(
        threshold=[
            {"level": "warning", "value": 70, "method": ">"},
            {"level": "critical", "value": 90, "method": ">="},
            {"level": "fatal", "value": 99},  # invalid level skipped
            {"level": "error", "value": None},
        ]
    )
    assert present_policy_thresholds(policy) == [
        {"level": "warning", "value": 70.0, "operator": ">", "label": "警告"},
        {"level": "critical", "value": 90.0, "operator": ">=", "label": "严重"},
    ]


def test_present_alert_dimensions_empty_and_sorted():
    assert present_alert_dimensions({}) == []
    assert present_alert_dimensions(None) == []
    assert present_alert_dimensions({"device": "eth0", "mount": "/"}) == [
        {"key": "device", "label": "device", "displayValue": "eth0"},
        {"key": "mount", "label": "mount", "displayValue": "/"},
    ]


def test_metric_display_name_never_falls_back_to_policy_name():
    policy = SimpleNamespace(
        name="application3D 本地演示策略",
        alert_name="CPU 使用率过高",
        query_condition={},
    )
    assert resolve_policy_metric_display_name(policy) is None


def test_alert_duration_active_uses_now(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from django.utils import timezone as dj_tz

    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dj_tz, "now", lambda: now)
    alert = SimpleNamespace(
        start_event_time=now - timedelta(minutes=5),
        end_event_time=None,
    )
    assert alert_duration_seconds(alert) == 300


def test_alert_duration_uses_end_when_present():
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    alert = SimpleNamespace(
        start_event_time=start,
        end_event_time=start + timedelta(seconds=42),
    )
    assert alert_duration_seconds(alert) == 42
