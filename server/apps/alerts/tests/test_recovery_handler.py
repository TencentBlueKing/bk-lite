"""告警恢复处理器与恢复检查器覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-告警.md：RECOVERY/CLOSED 事件按 external_id 关联到活跃告警；
当告警的所有 CREATED 事件都有更晚的恢复事件时，自动置为已恢复。
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.alerts.aggregation.recovery.recovery_checker import AlertRecoveryChecker, _attach_fallback_recoveries
from apps.alerts.aggregation.recovery.recovery_handler import RecoveryHandler
from apps.alerts.constants.constants import AlertStatus, EventAction
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event


@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="源1", source_id="s1", source_type="restful", secret="x")


def _make_event(source, event_id, external_id="ext-1", action=EventAction.CREATED, start_minutes_ago=10, **over):
    defaults = dict(
        source=source,
        raw_data={},
        title="t",
        level="0",
        start_time=timezone.now() - timedelta(minutes=start_minutes_ago),
        event_id=event_id,
        external_id=external_id,
        action=action,
        item="cpu",
        resource_name="host1",
    )
    defaults.update(over)
    return Event.objects.create(**defaults)


def _make_active_alert(*events, alert_id="A1"):
    alert = Alert.objects.create(
        alert_id=alert_id,
        level="0",
        title="t",
        content="c",
        fingerprint="fp",
        status=AlertStatus.PENDING,
    )
    for e in events:
        alert.events.add(e)
    return alert


def _fallback_events(
    source,
    *,
    created_team,
    recovery_team,
    created_push,
    recovery_push,
    created_event_id,
    recovery_event_id,
    external_id,
    alert_id,
):
    created = _make_event(
        source,
        created_event_id,
        external_id=external_id,
        action=EventAction.CREATED,
        start_minutes_ago=30,
        team=created_team,
        push_source_id=created_push,
        item="cpu",
        resource_name="shared-host",
        resource_id="",
        resource_type="",
    )
    alert = _make_active_alert(created, alert_id=alert_id)
    alert.team = list(created_team)
    alert.save(update_fields=["team"])
    recovery = _make_event(
        source,
        recovery_event_id,
        external_id=external_id,
        action=EventAction.RECOVERY,
        start_minutes_ago=5,
        team=recovery_team,
        push_source_id=recovery_push,
        item="cpu",
        resource_name="shared-host",
        resource_id="",
        resource_type="",
    )
    return alert, recovery


def _snapshot(alert, push_source_ids):
    alert.push_source_ids = list(push_source_ids)
    alert.save(update_fields=["push_source_ids"])
    alert.refresh_from_db()
    return (
        tuple(alert.events.order_by("event_id").values_list("event_id", flat=True)),
        list(alert.push_source_ids),
        alert.status,
    )


def _current_snapshot(alert):
    alert.refresh_from_db()
    return (
        tuple(alert.events.order_by("event_id").values_list("event_id", flat=True)),
        list(alert.push_source_ids),
        alert.status,
    )


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
    base = dict(item="cpu", resource_name="host", source=SimpleNamespace(source_id="s1"), source_id=5)
    ordered = SimpleNamespace(**base, team=[2, 1])
    reversed_team = SimpleNamespace(**base, team=[1, 2])
    other_org = SimpleNamespace(**base, team=[3])
    expected = (5, "cpu", "host", "s1", ("1", "2"))
    assert RecoveryHandler._build_fallback_key(ordered) == expected
    assert RecoveryHandler._build_fallback_key(reversed_team) == expected
    assert RecoveryHandler._build_fallback_key(other_org) != expected


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
def test_handle_recovery_matches_source_push_source_and_team(source):
    other_source = AlertSource.objects.create(name="源2", source_id="s2", source_type="restful", secret="x")
    created_expected = _make_event(source, "E-created-expected", external_id="same-ext", push_source_id="p1", team=[1])
    created_other_source = _make_event(other_source, "E-created-source", external_id="same-ext", push_source_id="p1", team=[1])
    created_other_team = _make_event(source, "E-created-team", external_id="same-ext", push_source_id="p1", team=[2])
    expected_alert = _make_active_alert(created_expected, alert_id="A-expected")
    other_source_alert = _make_active_alert(created_other_source, alert_id="A-other-source")
    other_team_alert = _make_active_alert(created_other_team, alert_id="A-other-team")
    recovery = _make_event(
        source,
        "E-recovery",
        external_id="same-ext",
        action=EventAction.RECOVERY,
        start_minutes_ago=1,
        push_source_id="p1",
        team=[1],
    )

    RecoveryHandler.handle_recovery_events([recovery])

    assert expected_alert.events.filter(pk=recovery.pk).exists()
    assert not other_source_alert.events.filter(pk=recovery.pk).exists()
    assert not other_team_alert.events.filter(pk=recovery.pk).exists()


@pytest.mark.django_db
def test_handle_recovery_without_external_id_skipped(source):
    created = _make_event(source, "E1", external_id="ext-1", action=EventAction.CREATED)
    alert = _make_active_alert(created)
    recovery = _make_event(source, "E2", external_id=None, action=EventAction.RECOVERY, resource_id="rid", resource_type="rt")

    RecoveryHandler.handle_recovery_events([recovery])
    assert not alert.events.filter(event_id="E2").exists()


@pytest.mark.django_db
def test_handle_recovery_no_matching_alert(source):
    recovery = _make_event(source, "E2", external_id="ext-unmatched", action=EventAction.RECOVERY, resource_id="rid", resource_type="rt")
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
    assert alert.closed_at is not None


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
    created = _make_event(source, "E1", external_id="ext-1", action=EventAction.CREATED, start_minutes_ago=30)
    created.item = "cpu"
    created.resource_name = "host1"
    created.save()
    alert = _make_active_alert(created)
    recovery = _make_event(source, "E2", external_id="ext-1", action=EventAction.RECOVERY, start_minutes_ago=5)
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
    assert alert.closed_at is not None


@pytest.mark.django_db
def test_run_recovery_checks_recovers(source):
    created = _make_event(source, "E1", external_id="ext-1", action=EventAction.CREATED, start_minutes_ago=30)
    recovery = _make_event(source, "E2", external_id="ext-1", action=EventAction.RECOVERY, start_minutes_ago=5)
    alert = _make_active_alert(created, recovery)
    RecoveryHandler._run_recovery_checks([alert], total_events=1, total_added=1, total_skipped=0)
    alert.refresh_from_db()
    assert alert.status == AlertStatus.AUTO_RECOVERY
    assert alert.closed_at is not None


def _other_organization_case(source, alert_id):
    """组织 B 仅有一条活跃告警，并保留一条已经挂上的历史恢复。"""
    alert, recovery = _fallback_events(
        source,
        created_team=[2],
        recovery_team=[1],
        created_push="push-b",
        recovery_push="push-a",
        created_event_id=f"{alert_id}-created",
        recovery_event_id=f"{alert_id}-recovery",
        external_id=f"{alert_id}-ext",
        alert_id=alert_id,
    )
    historical = _make_event(
        source,
        f"{alert_id}-historical",
        external_id=f"{alert_id}-historical-ext",
        action=EventAction.RECOVERY,
        start_minutes_ago=4,
        team=[1],
        push_source_id="push-old",
        item="cpu",
        resource_name="shared-host",
        resource_id="",
        resource_type="",
    )
    alert.events.add(historical)
    before = _snapshot(alert, ["push-b", "push-old"])
    return alert, recovery, before


@pytest.mark.django_db
def test_unique_fallback_does_not_attach_other_organization(source):
    alert, recovery, before = _other_organization_case(source, "A-org-b-live")

    RecoveryHandler.handle_recovery_events([recovery])

    assert _current_snapshot(alert) == before
    assert not alert.events.filter(pk=recovery.pk).exists()


@pytest.mark.django_db
def test_unique_fallback_attaches_same_organization_across_push_sources(source):
    alert, recovery = _fallback_events(
        source,
        created_team=[2, 1],
        recovery_team=[1, 2],
        created_push="push-created",
        recovery_push="push-recovery",
        created_event_id="E-same-org-created",
        recovery_event_id="E-same-org-recovery",
        external_id="ext-same-org",
        alert_id="A-same-org-live",
    )

    RecoveryHandler.handle_recovery_events([recovery])

    assert alert.events.filter(pk=recovery.pk).exists()
    alert.refresh_from_db()
    assert alert.status == AlertStatus.PENDING


@pytest.mark.django_db
def test_attach_fallback_recoveries_skips_other_organization(source):
    alert, recovery, before = _other_organization_case(source, "A-org-b-history")

    added = _attach_fallback_recoveries(alert)

    assert added == 0
    assert _current_snapshot(alert) == before
    assert not alert.events.filter(pk=recovery.pk).exists()


@pytest.mark.django_db
def test_attach_fallback_recoveries_links_same_organization_across_push_sources(source):
    alert, recovery = _fallback_events(
        source,
        created_team=[2, 1],
        recovery_team=[1, 2],
        created_push="push-created",
        recovery_push="push-recovery",
        created_event_id="E-same-org-history-created",
        recovery_event_id="E-same-org-history-recovery",
        external_id="ext-same-org-history",
        alert_id="A-same-org-history",
    )

    added = _attach_fallback_recoveries(alert)

    assert added == 1
    assert alert.events.filter(pk=recovery.pk).exists()
