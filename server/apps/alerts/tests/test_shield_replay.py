"""监控源屏蔽事件在窗口结束后补准入。"""

import datetime

import pytest
from django.utils import timezone

from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
from apps.alerts.common.shield_replay import replay_settled_monitor_shields
from apps.alerts.common.source_adapter.constants import build_nats_source_config
from apps.alerts.common.source_adapter.nats import NatsAdapter
from apps.alerts.constants.constants import AlertStatus, EventAction, EventStatus, LevelType
from apps.alerts.models.alert_operator import AlarmStrategy, AlertShield
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event, Level

MONITOR = "lite-monitor"


@pytest.fixture
def levels(db):
    for level_id in (0, 1, 2, 3):
        Level.objects.create(
            level_id=level_id,
            level_name=f"L{level_id}",
            level_display_name=f"等级{level_id}",
            level_type=LevelType.EVENT,
        )


@pytest.fixture
def source(db):
    return AlertSource.objects.create(
        name="NATS",
        source_id="nats",
        source_type="nats",
        secret="src-secret",
        config=build_nats_source_config(),
    )


def _stamp(hours_ago):
    return timezone.now() - datetime.timedelta(hours=hours_ago)


def _event(
    source,
    event_id,
    *,
    push_source_id=MONITOR,
    action=EventAction.CREATED,
    status=EventStatus.SHIELD,
    external_id="alert-1",
    when=None,
    team=None,
):
    when = when or _stamp(3)
    return Event.objects.create(
        source=source,
        push_source_id=push_source_id,
        raw_data={
            "title": "cpu high",
            "level": "1",
            "external_id": external_id,
            "action": action,
            "start_time": str(int(when.timestamp())),
            "push_source_id": push_source_id,
        },
        title="cpu high",
        level="1",
        start_time=when,
        event_id=event_id,
        external_id=external_id,
        action=action,
        status=status,
        team=team if team is not None else [1],
    )


def _shield(name, *, active_now):
    if active_now:
        window = {"type": "day", "start_time": "00:00:00", "end_time": "23:59:59"}
    else:
        window = {"type": "one", "start_time": "2000-01-01 00:00:00", "end_time": "2000-01-01 01:00:00"}
    return AlertShield.objects.create(
        name=name,
        match_type="all",
        suppression_time=window,
        is_active=True,
        created_by="",
    )


@pytest.mark.django_db
def test_expired_shield_replays_unrecovered_monitor_event(levels, source):
    _shield("ended", active_now=False)
    original = _event(source, "E-created")

    result = replay_settled_monitor_shields()

    original.refresh_from_db()
    replayed = Event.objects.exclude(pk=original.pk).get()
    assert result["replayed"] == 1
    assert original.status == EventStatus.SHIELD
    assert original.shield_settled_at is not None
    assert replayed.external_id == "alert-1"
    assert replayed.action == EventAction.CREATED
    assert replayed.status == EventStatus.RECEIVED
    assert replayed.push_source_id == MONITOR
    assert replayed.raw_data["lifecycle_generation"] == "shield-replay:E-created"
    assert replayed.team == [1]


@pytest.mark.django_db
def test_shielded_recovery_settles_without_replay(levels, source):
    _shield("ended", active_now=False)
    created = _event(source, "E-created", when=_stamp(3))
    _event(
        source,
        "E-recovery",
        action=EventAction.RECOVERY,
        when=_stamp(1),
    )

    result = replay_settled_monitor_shields()

    created.refresh_from_db()
    assert result["replayed"] == 0
    assert result["settled"] == 1
    assert created.shield_settled_at is not None
    assert Event.objects.filter(action=EventAction.CREATED).count() == 1


@pytest.mark.django_db
def test_active_shield_leaves_event_unsettled(levels, source):
    _shield("open", active_now=True)
    original = _event(source, "E-created")

    result = replay_settled_monitor_shields()

    original.refresh_from_db()
    assert result == {"scanned": 1, "settled": 0, "replayed": 0}
    assert original.shield_settled_at is None
    assert Event.objects.count() == 1


@pytest.mark.django_db
def test_second_run_does_not_replay_again(levels, source):
    _shield("ended", active_now=False)
    _event(source, "E-created")

    replay_settled_monitor_shields()
    second = replay_settled_monitor_shields()

    assert second["scanned"] == 0
    assert Event.objects.filter(action=EventAction.CREATED).count() == 2


@pytest.mark.django_db
def test_other_push_sources_are_ignored(levels, source):
    _shield("ended", active_now=False)
    original = _event(source, "E-k8s", push_source_id="k8s")

    result = replay_settled_monitor_shields()

    original.refresh_from_db()
    assert result["scanned"] == 0
    assert original.shield_settled_at is None
    assert Event.objects.count() == 1


@pytest.mark.django_db
def test_active_alert_settles_without_replay(levels, source):
    _shield("ended", active_now=False)
    original = _event(source, "E-created")
    alert = Alert.objects.create(
        alert_id="ALERT-1",
        status=AlertStatus.UNASSIGNED,
        level="1",
        title="cpu high",
        content="cpu high",
        fingerprint="fp",
    )
    alert.events.add(original)

    result = replay_settled_monitor_shields()

    original.refresh_from_db()
    assert result["replayed"] == 0
    assert result["settled"] == 1
    assert original.shield_settled_at is not None
    assert Event.objects.count() == 1


def _ingest(source, external_id, action, when):
    payload = {
        "title": "CPU高",
        "description": "cpu > 90",
        "level": "1",
        "external_id": external_id,
        "action": action,
        "start_time": str(int(when.timestamp())),
        "push_source_id": MONITOR,
        "organizations": [1],
        "service": "svc-a",
        "item": "cpu",
        "resource_name": "host1",
    }
    if action == EventAction.RECOVERY:
        payload["end_time"] = str(int(timezone.now().timestamp()))
    NatsAdapter(alert_source=source, events=[payload], trusted_internal=True).main()


def _correlation_rule():
    for level_id in (0, 1, 2):
        Level.objects.create(
            level_id=level_id,
            level_name=f"A{level_id}",
            level_display_name=f"告警{level_id}",
            level_type=LevelType.ALERT,
        )
    AlarmStrategy.objects.create(
        name="降噪",
        strategy_type="smart_denoise",
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "title", "operator": "eq", "value": "CPU高"}]],
        params={"window_size": 60, "group_by": ["service"]},
    )


def _end_shield(shield):
    shield.suppression_time = {"type": "one", "start_time": "2000-01-01 00:00:00", "end_time": "2000-01-01 01:00:00"}
    shield.save(update_fields=["suppression_time"])


@pytest.mark.django_db
def test_window_end_without_another_monitor_push_still_opens_alert(levels, source):
    """复现：窗口内只有第一条监控事件，窗口结束后监控不再推送。"""
    shield = _shield("open", active_now=True)
    _correlation_rule()
    _ingest(source, "monitor-alert-9", EventAction.CREATED, _stamp(0))

    shielded = Event.objects.get(external_id="monitor-alert-9")
    assert shielded.status == EventStatus.SHIELD
    assert Alert.objects.exists() is False

    _end_shield(shield)
    assert Alert.objects.exists() is False
    assert Event.objects.filter(status=EventStatus.RECEIVED).exists() is False

    replay_settled_monitor_shields()
    AggregationProcessor().process_aggregation()

    shielded.refresh_from_db()
    opened = Alert.objects.get()
    assert shielded.status == EventStatus.SHIELD
    assert shielded.shield_settled_at is not None
    assert opened.status in AlertStatus.ACTIVATE_STATUS
    assert opened.events.filter(status=EventStatus.RECEIVED, external_id="monitor-alert-9").exists()


@pytest.mark.django_db
def test_window_end_with_shielded_recovery_does_not_open_alert(levels, source):
    shield = _shield("open", active_now=True)
    _correlation_rule()
    _ingest(source, "monitor-alert-9", EventAction.CREATED, _stamp(2))
    _ingest(source, "monitor-alert-9", EventAction.RECOVERY, _stamp(0))
    _end_shield(shield)

    replay_settled_monitor_shields()
    AggregationProcessor().process_aggregation()

    assert Alert.objects.exists() is False
    assert Event.objects.filter(shield_settled_at__isnull=False, action=EventAction.CREATED).exists()
