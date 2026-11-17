"""未恢复监控告警：严重度排序在截断前完成，默认仍是最新 10 条。"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject
from apps.monitor.models.monitor_policy import MonitorAlert, MonitorPolicy
from apps.monitor.nats import monitor as monitor_nats
from apps.monitor.services.active_alert_ranking import format_active_alert_duration, parse_active_alert_order

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_parse_active_alert_order_defaults_to_latest_and_rejects_unknown():
    assert parse_active_alert_order(None) == "latest"
    assert parse_active_alert_order("") == "latest"
    assert parse_active_alert_order(" Severity ") == "severity"
    with pytest.raises(ValueError, match="order"):
        parse_active_alert_order("value")


def test_format_active_alert_duration_is_not_raw_seconds():
    assert format_active_alert_duration(None, NOW) == "--"
    assert format_active_alert_duration(NOW - timedelta(seconds=30), NOW) == "不到1分钟"
    assert format_active_alert_duration(NOW - timedelta(minutes=45), NOW) == "45分钟"
    assert format_active_alert_duration(NOW - timedelta(hours=1, minutes=30), NOW) == "1小时30分钟"
    assert format_active_alert_duration(NOW - timedelta(hours=3), NOW) == "3小时"
    assert format_active_alert_duration(NOW - timedelta(days=2), NOW) == "2天"
    assert format_active_alert_duration(NOW - timedelta(days=2, hours=3), NOW) == "2天3小时"


def _policy(name):
    monitor_object = MonitorObject.objects.create(name=f"{name}-object", level="base")
    return MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name=name,
        organizations=[1],
        algorithm="max",
        query_condition={"type": "pmq", "query": "up"},
        source={},
        group_by=[],
    )


def _alert(policy, instance, *, level, start, name, organizations=None, status="new", value=1):
    alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        organizations=organizations if organizations is not None else [1],
        monitor_instance_id=instance.id,
        monitor_instance_name=name,
        level=level,
        status=status,
        value=value,
        start_event_time=start,
    )
    return alert


def _patch_scope(monkeypatch, policy, instance):
    user = SimpleNamespace(username="overview-user", domain="domain.com")
    monkeypatch.setattr(
        monitor_nats,
        "_get_nats_actor_scope",
        lambda user_info: (user, 1, False, frozenset({1}), False, None),
    )
    monkeypatch.setattr(
        monitor_nats,
        "_resolve_latest_active_alert_instances",
        lambda *args, **kwargs: ({str(instance.id): instance}, None),
    )
    monkeypatch.setattr(
        monitor_nats,
        "_get_nats_accessible_policy_queryset",
        lambda user_info: (MonitorPolicy.objects.filter(id=policy.id), None),
    )
    monkeypatch.setattr(monitor_nats.timezone, "now", lambda: NOW)


def _seed():
    policy = _policy("severity-overview")
    instance = MonitorInstance.objects.create(
        id="severity-host",
        name="主机甲",
        monitor_object=policy.monitor_object,
        is_active=True,
    )
    created = {}
    created["fatal"] = _alert(
        policy,
        instance,
        level="fatal",
        start=NOW - timedelta(days=30),
        name="未知级别",
        value=999,
    )
    created["critical_early"] = _alert(
        policy,
        instance,
        level="critical",
        start=NOW - timedelta(days=2, hours=3),
        name="严重甲",
        value=1,
    )
    created["critical_late"] = _alert(
        policy,
        instance,
        level="Critical",
        start=NOW - timedelta(days=2, hours=3),
        name="严重乙",
        value=2,
    )
    created["error"] = _alert(policy, instance, level="error", start=NOW - timedelta(days=1), name="错误")
    created["warning_early"] = _alert(policy, instance, level="warning", start=NOW - timedelta(hours=10), name="警告甲")
    created["warning_late"] = _alert(policy, instance, level="warning", start=NOW - timedelta(hours=9), name="警告乙")
    created["info"] = _alert(policy, instance, level="info", start=NOW - timedelta(hours=8), name="提醒")
    created["no_data"] = _alert(policy, instance, level="no_data", start=NOW - timedelta(days=20), name="无数据")
    created["recovered"] = _alert(
        policy,
        instance,
        level="critical",
        start=NOW - timedelta(days=40),
        name="已恢复",
        status="recovered",
    )
    created["foreign"] = _alert(
        policy,
        instance,
        level="critical",
        start=NOW - timedelta(days=40),
        name="其他组织",
        organizations=[2],
    )
    fillers = []
    for index in range(11):
        fillers.append(
            _alert(
                policy,
                instance,
                level="info",
                start=NOW - timedelta(minutes=index + 1),
                name=f"最新{index}",
            )
        )
    created["fillers"] = fillers
    MonitorAlert.objects.filter(id=created["critical_early"].id).update(created_at=NOW - timedelta(days=5))
    MonitorAlert.objects.filter(id=created["critical_late"].id).update(created_at=NOW - timedelta(days=4))
    return policy, instance, created


@pytest.mark.django_db
def test_default_latest_alerts_stay_newest_ten_and_omit_duration_text(monkeypatch):
    policy, instance, created = _seed()
    _patch_scope(monkeypatch, policy, instance)

    response = monitor_nats.query_latest_active_alerts({}, user_info={"user": "overview-user", "team": 1})

    assert response["result"] is True
    items = response["data"]["items"]
    assert [item["id"] for item in items] == [item.id for item in created["fillers"][:10]]
    assert created["critical_early"].id not in {item["id"] for item in items}
    assert "duration_text" not in items[0]
    assert response["data"]["count"] == 19


@pytest.mark.django_db
def test_severity_order_ranks_full_authorized_set_before_taking_five(monkeypatch):
    policy, instance, created = _seed()
    _patch_scope(monkeypatch, policy, instance)

    response = monitor_nats.query_latest_active_alerts(
        {"order": "severity", "limit": 5},
        user_info={"user": "overview-user", "team": 1},
    )

    assert response["result"] is True
    items = response["data"]["items"]
    assert [item["id"] for item in items] == [
        created["critical_early"].id,
        created["critical_late"].id,
        created["error"].id,
        created["warning_early"].id,
        created["warning_late"].id,
    ]
    assert items[0]["value"] == 1
    assert items[0]["duration_text"] == "2天3小时"
    assert items[1]["duration_text"] == "2天3小时"
    assert response["data"]["count"] == 19
    dropped = {
        created["fatal"].id,
        created["no_data"].id,
        created["info"].id,
        created["foreign"].id,
        created["recovered"].id,
    }
    assert dropped.isdisjoint({item["id"] for item in items})

    full = monitor_nats.query_latest_active_alerts(
        {"order": "severity", "limit": 100},
        user_info={"user": "overview-user", "team": 1},
    )
    full_ids = [item["id"] for item in full["data"]["items"]]
    assert full_ids.index(created["no_data"].id) < full_ids.index(created["fatal"].id)
    assert created["foreign"].id not in full_ids
    assert created["recovered"].id not in full_ids


def test_invalid_alert_order_does_not_fall_back_to_latest():
    response = monitor_nats.query_latest_active_alerts({"order": "value"})
    assert response["result"] is False
    assert "order" in response["message"]
