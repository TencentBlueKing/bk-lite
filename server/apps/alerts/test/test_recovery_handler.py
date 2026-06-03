"""告警恢复处理器与恢复检查器覆盖测试。

对照 spec/prd/告警中心·告警：RECOVERY/CLOSED 事件按 external_id 关联到活跃告警；
当告警的所有 CREATED 事件都有更晚的恢复事件时，自动置为已恢复。
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.alerts.aggregation.recovery.recovery_checker import AlertRecoveryChecker
from apps.alerts.aggregation.recovery.recovery_handler import RecoveryHandler
from apps.alerts.constants.constants import AlertStatus, EventAction
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event


@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="源1", source_id="s1", source_type="restful", secret="x")


def _make_event(source, event_id, external_id="ext-1", action=EventAction.CREATED, start_minutes_ago=10, **over):
    defaults = dict(
        source=source, raw_data={}, title="t", level="0",
        start_time=timezone.now() - timedelta(minutes=start_minutes_ago),
        event_id=event_id, external_id=external_id, action=action,
        item="cpu", resource_name="host1",
    )
    defaults.update(over)
    return Event.objects.create(**defaults)


def _make_active_alert(*events, alert_id="A1"):
    alert = Alert.objects.create(
        alert_id=alert_id, level="0", title="t", content="c", fingerprint="fp",
        status=AlertStatus.PENDING,
    )
    for e in events:
        alert.events.add(e)
    return alert


# --------------------------------------------------------------------------
# 纯函数
# --------------------------------------------------------------------------


def test_normalize_value():
    assert RecoveryHandler._normalize_value(None) == ""
    assert RecoveryHandler._normalize_value("  x ") == "x"


def test_build_fallback_key_missing_fields():
    event = SimpleNamespace(item="", resource_name="r", source=SimpleNamespace(source_id="s"), source_id=1)
    assert RecoveryHandler._build_fallback_key(event) is None


def test_build_fallback_key_complete():
    event = SimpleNamespace(item="cpu", resource_name="host", source=SimpleNamespace(source_id="s1"), source_id=5)
    assert RecoveryHandler._build_fallback_key(event) == (5, "cpu", "host", "s1")


def test_supports_unique_fallback():
    assert RecoveryHandler._supports_unique_fallback(SimpleNamespace(resource_id="", resource_type="")) is True
    assert RecoveryHandler._supports_unique_fallback(SimpleNamespace(resource_id="1", resource_type="")) is False


# --------------------------------------------------------------------------
# handle_recovery_events 关联行为
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_handle_recovery_events_empty_returns_none():
    assert RecoveryHandler.handle_recovery_events([]) is None


@pytest.mark.django_db
def test_handle_recovery_associates_event_to_alert(source):
    created = _make_event(source, "E1", external_id="ext-1", action=EventAction.CREATED, start_minutes_ago=20)
    alert = _make_active_alert(created)
    recovery = _make_event(source, "E2", external_id="ext-1", action=EventAction.RECOVERY, start_minutes_ago=5)

    RecoveryHandler.handle_recovery_events([recovery])

    # 恢复事件被同步关联到告警
    assert alert.events.filter(event_id="E2").exists()


@pytest.mark.django_db
def test_handle_recovery_without_external_id_skipped(source):
    created = _make_event(source, "E1", external_id="ext-1", action=EventAction.CREATED)
    alert = _make_active_alert(created)
    recovery = _make_event(source, "E2", external_id=None, action=EventAction.RECOVERY,
                           resource_id="rid", resource_type="rt")

    RecoveryHandler.handle_recovery_events([recovery])
    assert not alert.events.filter(event_id="E2").exists()


@pytest.mark.django_db
def test_handle_recovery_no_matching_alert(source):
    recovery = _make_event(source, "E2", external_id="ext-unmatched", action=EventAction.RECOVERY,
                           resource_id="rid", resource_type="rt")
    # 不抛异常
    RecoveryHandler.handle_recovery_events([recovery])


# --------------------------------------------------------------------------
# AlertRecoveryChecker.check_and_recover_alert（同步）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_check_and_recover_all_recovered(source):
    created = _make_event(source, "E1", external_id="ext-1", action=EventAction.CREATED, start_minutes_ago=30)
    recovery = _make_event(source, "E2", external_id="ext-1", action=EventAction.RECOVERY, start_minutes_ago=5)
    alert = _make_active_alert(created, recovery)

    result = AlertRecoveryChecker.check_and_recover_alert(alert)
    assert result is True
    alert.refresh_from_db()
    assert alert.status == AlertStatus.AUTO_RECOVERY


@pytest.mark.django_db
def test_check_and_recover_unrecovered_stays_active(source):
    created = _make_event(source, "E1", external_id="ext-1", action=EventAction.CREATED, start_minutes_ago=5)
    # 恢复事件比创建事件更早 → 不算恢复
    recovery = _make_event(source, "E2", external_id="ext-1", action=EventAction.RECOVERY, start_minutes_ago=30)
    alert = _make_active_alert(created, recovery)

    result = AlertRecoveryChecker.check_and_recover_alert(alert)
    assert result is False
    alert.refresh_from_db()
    assert alert.status == AlertStatus.PENDING


@pytest.mark.django_db
def test_check_and_recover_no_events(source):
    alert = _make_active_alert()
    assert AlertRecoveryChecker.check_and_recover_alert(alert) is False


@pytest.mark.django_db
def test_handle_recovery_via_fallback_key(source):
    # 恢复事件无 external_id 但有 item+resource_name（无 resource_id/type）→ 通过回退键匹配
    created = _make_event(source, "E1", external_id="ext-1", action=EventAction.CREATED,
                          start_minutes_ago=30)
    created.item = "cpu"
    created.resource_name = "host1"
    created.save()
    alert = _make_active_alert(created)
    recovery = _make_event(source, "E2", external_id="ext-1", action=EventAction.RECOVERY,
                           start_minutes_ago=5)
    RecoveryHandler.handle_recovery_events([recovery])
    assert alert.events.filter(event_id="E2").exists()


@pytest.mark.django_db
def test_check_and_recover_closed_action(source):
    created = _make_event(source, "E1", external_id="ext-1", action=EventAction.CREATED, start_minutes_ago=30)
    closed = _make_event(source, "E2", external_id="ext-1", action=EventAction.CLOSED, start_minutes_ago=5)
    alert = _make_active_alert(created, closed)
    assert AlertRecoveryChecker.check_and_recover_alert(alert) is True
    alert.refresh_from_db()
    assert alert.status == AlertStatus.AUTO_RECOVERY


@pytest.mark.django_db
def test_run_recovery_checks_recovers(source):
    created = _make_event(source, "E1", external_id="ext-1", action=EventAction.CREATED, start_minutes_ago=30)
    recovery = _make_event(source, "E2", external_id="ext-1", action=EventAction.RECOVERY, start_minutes_ago=5)
    alert = _make_active_alert(created, recovery)
    RecoveryHandler._run_recovery_checks([alert], total_events=1, total_added=1, total_skipped=0)
    alert.refresh_from_db()
    assert alert.status == AlertStatus.AUTO_RECOVERY
