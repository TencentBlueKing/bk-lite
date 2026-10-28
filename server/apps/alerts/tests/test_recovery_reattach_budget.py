"""恢复补挂只拿每个完整键的最早创建时间做一次严格大于比较。"""

import pytest
from django.utils import timezone

from apps.alerts.aggregation.recovery.match_key import build_recovery_match_key
from apps.alerts.aggregation.recovery.recovery_checker import (
    AlertRecoveryChecker,
    attach_visible_recoveries,
)
from apps.alerts.constants.constants import AlertStatus, EventAction
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event


class _Instant:
    def __init__(self, rank, counter):
        self.rank = rank
        self.counter = counter

    def __gt__(self, other):
        if not isinstance(other, _Instant):
            return NotImplemented
        self.counter[0] += 1
        return self.rank > other.rank

    def __lt__(self, other):
        if not isinstance(other, _Instant):
            return NotImplemented
        return self.rank < other.rank

    def __eq__(self, other):
        if not isinstance(other, _Instant):
            return NotImplemented
        return self.rank == other.rank


def _install_sentinels(monkeypatch, ranks):
    counter = [0]

    def _instant(event):
        return _Instant(ranks[event.pk], counter)

    monkeypatch.setattr(AlertRecoveryChecker, "_get_created_event_time", _instant)
    monkeypatch.setattr(AlertRecoveryChecker, "_get_recovery_event_time", _instant)
    return counter


def _source(source_id):
    return AlertSource.objects.create(name=source_id, source_id=source_id, source_type="restful", secret="x")


def _event(source, event_id, *, action, external_id, team, item="cpu", resource_name="host-a"):
    return Event.objects.create(
        source=source,
        raw_data={},
        title="t",
        level="0",
        start_time=timezone.now(),
        event_id=event_id,
        external_id=external_id,
        action=action,
        item=item,
        resource_name=resource_name,
        resource_id="",
        resource_type="",
        team=team,
        push_source_id="push-1",
    )


def _alert(alert_id, *events):
    alert = Alert.objects.create(
        alert_id=alert_id,
        level="0",
        title="t",
        content="c",
        fingerprint=alert_id[:32],
        status=AlertStatus.PENDING,
        team=[1],
    )
    for event in events:
        alert.events.add(event)
    return alert


def _event_ids(alert):
    return set(alert.events.values_list("event_id", flat=True))


@pytest.mark.django_db
def test_all_older_recoveries_compare_once_per_recovery(monkeypatch):
    observed = {}
    for size in (10, 20):
        source = _source(f"budget-{size}")
        external_id = f"ext-{size}"
        ranks = {}
        created = []
        for index in range(size):
            event = _event(
                source,
                f"c-{size}-{index}",
                action=EventAction.CREATED,
                external_id=external_id,
                team=[1],
            )
            ranks[event.pk] = 1000 + index
            created.append(event)
        for index in range(size):
            event = _event(
                source,
                f"r-{size}-{index}",
                action=EventAction.RECOVERY,
                external_id=external_id,
                team=[1],
            )
            ranks[event.pk] = index
        other_created = _event(
            source,
            f"c-{size}-other",
            action=EventAction.CREATED,
            external_id=external_id,
            team=[2],
        )
        other_recovery = _event(
            source,
            f"r-{size}-other",
            action=EventAction.RECOVERY,
            external_id=external_id,
            team=[2],
        )
        ranks[other_created.pk] = 8000
        ranks[other_recovery.pk] = 9000
        alert = _alert(f"A-{size}", *created)
        other = _alert(f"A-{size}-other", other_created)
        other.team = [2]
        other.save(update_fields=["team"])
        before = _event_ids(other)
        assert build_recovery_match_key(created[0]) != build_recovery_match_key(other_created)

        counter = _install_sentinels(monkeypatch, ranks)
        added = attach_visible_recoveries(alert)

        assert added == 0
        assert _event_ids(alert) == {event.event_id for event in created}
        assert _event_ids(other) == before
        assert other_recovery.event_id not in _event_ids(alert)
        observed[size] = counter[0]

    assert observed == {10: 10, 20: 20}


@pytest.mark.django_db
def test_recovery_equal_to_earliest_created_time_does_not_attach(monkeypatch):
    source = _source("equal-source")
    earlier = _event(source, "c-equal-early", action=EventAction.CREATED, external_id="ext-equal", team=[1])
    later = _event(source, "c-equal-late", action=EventAction.CREATED, external_id="ext-equal", team=[1])
    recovery = _event(source, "r-equal", action=EventAction.RECOVERY, external_id="ext-equal", team=[1])
    alert = _alert("A-equal", earlier, later)
    _install_sentinels(monkeypatch, {earlier.pk: 10, later.pk: 40, recovery.pk: 10})

    assert attach_visible_recoveries(alert) == 0
    assert recovery.event_id not in _event_ids(alert)


@pytest.mark.django_db
def test_recovery_later_than_earliest_created_time_attaches_once(monkeypatch):
    source = _source("later-source")
    earlier = _event(source, "c-later-early", action=EventAction.CREATED, external_id="ext-later", team=[1])
    later = _event(source, "c-later-late", action=EventAction.CREATED, external_id="ext-later", team=[1])
    recovery = _event(source, "r-later", action=EventAction.RECOVERY, external_id="ext-later", team=[1])
    alert = _alert("A-later", earlier, later)
    _install_sentinels(monkeypatch, {earlier.pk: 10, later.pk: 40, recovery.pk: 11})

    assert attach_visible_recoveries(alert) == 1
    assert attach_visible_recoveries(alert) == 0
    assert _event_ids(alert) == {"c-later-early", "c-later-late", "r-later"}


@pytest.mark.django_db
def test_fallback_older_recoveries_compare_once_per_recovery(monkeypatch):
    observed = {}
    for size in (10, 20):
        source = _source(f"fallback-{size}")
        item = f"cpu-{size}"
        ranks = {}
        created = []
        for index in range(size):
            event = _event(
                source,
                f"fc-{size}-{index}",
                action=EventAction.CREATED,
                external_id=f"created-{size}",
                team=[1],
                item=item,
            )
            ranks[event.pk] = 1000 + index
            created.append(event)
        for index in range(size):
            event = _event(
                source,
                f"fr-{size}-{index}",
                action=EventAction.RECOVERY,
                external_id=f"recovery-{size}-{index}",
                team=[1],
                item=item,
            )
            ranks[event.pk] = index
        alert = _alert(f"F-{size}", *created)
        counter = _install_sentinels(monkeypatch, ranks)

        assert attach_visible_recoveries(alert) == 0
        assert _event_ids(alert) == {event.event_id for event in created}
        observed[size] = counter[0]

    assert observed == {10: 10, 20: 20}
