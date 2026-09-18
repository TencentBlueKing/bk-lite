import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event
from apps.alerts.service.push_source_counts import MemoryHashStore, PushSourceCountCache

pytestmark = [pytest.mark.unit]


def counts():
    return PushSourceCountCache(store=MemoryHashStore())


def _event(source_id="k8s", push_source_id="cluster-a", team=(1,)):
    return SimpleNamespace(
        source=SimpleNamespace(source_id=source_id),
        push_source_id=push_source_id,
        team=list(team),
    )


def test_observe_increments_per_team_and_source():
    cache = counts()
    cache.observe_events(
        [
            _event("k8s", "cluster-a", [1]),
            _event("k8s", "cluster-a", [1]),
            _event("k8s", "cluster-b", [1]),
            _event("nats", "cluster-a", [1]),
            _event("k8s", "cluster-a", [2]),
        ]
    )
    cache.store.set(cache.ready_key(1, "k8s"), 1)
    cache.store.set(cache.ready_key(1, "nats"), 1)
    cache.store.set(cache.ready_key(2, "k8s"), 1)
    assert cache.list_for_source([1], "k8s") == [
        {"id": "cluster-a", "count": 2},
        {"id": "cluster-b", "count": 1},
    ]
    assert cache.list_for_source([1], "nats") == [{"id": "cluster-a", "count": 1}]
    assert cache.list_for_source([2], "k8s") == [{"id": "cluster-a", "count": 1}]


def test_observe_skips_empty_team_and_blank_ids():
    cache = counts()
    cache.observe_events(
        [
            _event("k8s", "cluster-a", []),
            _event("k8s", "", [1]),
            _event("", "cluster-a", [1]),
            _event("k8s", "  ", [1]),
        ]
    )
    cache.store.set(cache.ready_key(1, "k8s"), 1)
    assert cache.list_for_source([1], "k8s") == []


def test_observe_survives_store_errors():
    class Boom(MemoryHashStore):
        def hincrby(self, key, field, amount):
            raise RuntimeError("redis down")

    cache = PushSourceCountCache(store=Boom())
    cache.observe_events([_event()])


def test_cap_rejects_new_members_and_keeps_incrementing_existing():
    cache = counts()
    cache.MAX_MEMBERS = 2
    cache.observe_events([_event("k8s", "a", [1]), _event("k8s", "b", [1])])
    cache.observe_events([_event("k8s", "c", [1]), _event("k8s", "a", [1])])
    cache.store.set(cache.ready_key(1, "k8s"), 1)
    rows = cache.list_for_source([1], "k8s")
    assert {row["id"] for row in rows} == {"a", "b"}
    assert next(row["count"] for row in rows if row["id"] == "a") == 2
    assert next(row["count"] for row in rows if row["id"] == "b") == 1


def test_observe_store_error_logs_type_without_payload(caplog, capsys):
    sentinel = "redis-down-secret-payload"
    source_sentinel = "cluster-secret-id"

    class Boom(MemoryHashStore):
        def hincrby(self, key, field, amount):
            raise RuntimeError(sentinel)

    cache = PushSourceCountCache(store=Boom())
    with caplog.at_level(logging.WARNING, logger="alert"):
        cache.observe_events([_event("k8s", source_sentinel, [1])])
    records = [record for record in caplog.records if record.name == "alert"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.msg == "push source counts observe failed: team_id=%s source_id=%s error_type=%s"
    assert record.args == (1, "k8s", "RuntimeError")
    blob = repr(record.args) + logging.Formatter().format(record) + caplog.text + capsys.readouterr().out
    assert sentinel not in blob
    assert source_sentinel not in blob


def test_list_sums_child_teams():
    cache = counts()
    cache.observe_events([_event("k8s", "cluster-a", [1]), _event("k8s", "cluster-a", [2])])
    cache.store.set(cache.ready_key(1, "k8s"), 1)
    cache.store.set(cache.ready_key(2, "k8s"), 1)
    assert cache.list_for_source([1, 2], "k8s") == [{"id": "cluster-a", "count": 2}]


@pytest.mark.django_db
def test_cold_start_rebuilds_from_recent_events():
    source = AlertSource.objects.create(name="K8s", source_id="k8s", source_type="restful", secret="s")
    other = AlertSource.objects.create(name="NATS", source_id="nats", source_type="nats", secret="s")
    now = timezone.now()
    Event.objects.create(
        source=source,
        raw_data={},
        title="a",
        level="1",
        start_time=now,
        event_id="E1",
        ingest_key="k1",
        push_source_id="cluster-a",
        team=[1],
    )
    Event.objects.create(
        source=source,
        raw_data={},
        title="b",
        level="1",
        start_time=now,
        event_id="E2",
        ingest_key="k2",
        push_source_id="cluster-a",
        team=[1],
    )
    Event.objects.create(
        source=other,
        raw_data={},
        title="c",
        level="1",
        start_time=now,
        event_id="E3",
        push_source_id="cluster-a",
        team=[1],
    )
    old = Event.objects.create(
        source=source,
        raw_data={},
        title="old",
        level="1",
        start_time=now,
        event_id="E4",
        push_source_id="stale",
        team=[1],
    )
    Event.objects.filter(pk=old.pk).update(received_at=now - timedelta(days=91))
    cache = counts()
    assert cache.list_for_source([1], "k8s") == [{"id": "cluster-a", "count": 2}]
