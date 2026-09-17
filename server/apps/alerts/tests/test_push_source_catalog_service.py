import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.alerts.models import Alert
from apps.alerts.service import push_source_catalog as catalog_mod
from apps.alerts.service.push_source_catalog import MemoryCatalogStore, PushSourceCatalog

pytestmark = [pytest.mark.unit]


def catalog():
    return PushSourceCatalog(store=MemoryCatalogStore(), now=lambda: 1_700_000_000, min_interval=60)


@pytest.mark.django_db
def test_observe_keeps_original_identity_per_team():
    cat = catalog()
    cat.observe([1], ["prod", "001", "1", "", "  "])
    cat.observe([2], ["other"])
    assert cat.list_for_teams([1]) == ["001", "1", "prod"]
    assert cat.list_for_teams([2]) == ["other"]
    assert cat.list_for_teams([1, 2]) == ["001", "1", "other", "prod"]


def test_observe_refreshes_score_and_skips_within_interval():
    ticks = iter([100, 110, 200])
    cat = PushSourceCatalog(store=MemoryCatalogStore(), now=lambda: next(ticks), min_interval=60)
    cat.observe([1], ["prod"])
    cat.observe([1], ["prod"])
    assert cat.store.zscore("alerts:push_source_ids:v1:1", "prod") == 100
    cat.observe([1], ["prod"])
    assert cat.store.zscore("alerts:push_source_ids:v1:1", "prod") == 200


@pytest.mark.django_db
def test_cap_rejects_new_members_and_keeps_existing():
    cat = catalog()
    cat.observe([1], [f"s{i}" for i in range(PushSourceCatalog.MAX_MEMBERS)])
    cat.observe([1], ["overflow", "s0"])
    members = cat.list_for_teams([1])
    assert len(members) == PushSourceCatalog.MAX_MEMBERS
    assert "s0" in members
    assert "overflow" not in members


def test_observe_ignores_empty_team_and_survives_store_errors():
    class Boom(MemoryCatalogStore):
        def zadd(self, key, mapping):
            raise RuntimeError("redis down")

    cat = PushSourceCatalog(store=Boom(), now=lambda: 1, min_interval=0)
    cat.observe([], ["prod"])
    cat.observe([1], ["prod"])


def test_list_omits_scores_older_than_stale_window():
    now = 1_700_000_000
    cat = PushSourceCatalog(store=MemoryCatalogStore(), now=lambda: now, min_interval=0)
    cat.store.zadd(
        "alerts:push_source_ids:v1:1",
        {"fresh": now, "stale": now - PushSourceCatalog.STALE_SECONDS - 1},
    )
    cat.store.set("alerts:push_source_ids:ready:v1:1", 1)
    assert cat.list_for_teams([1]) == ["fresh"]


def test_cap_logs_bounded_counts_without_member_ids(caplog, capsys):
    rejected_id = "overflow-secret-id"
    cat = catalog()
    cat.observe([1], [f"s{i}" for i in range(PushSourceCatalog.MAX_MEMBERS)])
    with caplog.at_level(logging.INFO, logger="alert"):
        cat.observe([1], [rejected_id, "s0"])
    records = [record for record in caplog.records if record.name == "alert"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.INFO
    assert record.msg == "push source catalog cap reached: team_id=%s size=%s rejected=%s"
    assert record.args == (1, PushSourceCatalog.MAX_MEMBERS, 1)
    assert record.getMessage() == f"push source catalog cap reached: team_id=1 size={PushSourceCatalog.MAX_MEMBERS} rejected=1"
    assert record.exc_info is None
    output = capsys.readouterr()
    blob = repr(record.args) + logging.Formatter().format(record) + caplog.text + output.out + output.err
    assert rejected_id not in blob


def test_observe_store_error_logs_type_without_payload(caplog, capsys):
    sentinel = "redis-down-secret-payload"
    source_sentinel = "prod-secret-id"

    class Boom(MemoryCatalogStore):
        def zadd(self, key, mapping):
            raise RuntimeError(sentinel)

    cat = PushSourceCatalog(store=Boom(), now=lambda: 1, min_interval=0)
    with caplog.at_level(logging.WARNING, logger="alert"):
        cat.observe([1], [source_sentinel])
    records = [record for record in caplog.records if record.name == "alert"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.msg == "push source catalog observe failed: team_id=%s error_type=%s"
    assert record.args == (1, "RuntimeError")
    assert record.getMessage() == "push source catalog observe failed: team_id=1 error_type=RuntimeError"
    assert record.exc_info is None
    output = capsys.readouterr()
    blob = repr(record.args) + logging.Formatter().format(record) + caplog.text + output.out + output.err
    assert sentinel not in blob
    assert source_sentinel not in blob


def test_default_store_uses_django_redis_cache_client(monkeypatch):
    fake_client = object()
    backend = SimpleNamespace(_cache=SimpleNamespace(get_client=lambda key, write: fake_client))
    monkeypatch.setattr(catalog_mod, "cache", backend)
    store = catalog_mod._build_default_store()
    assert isinstance(store, catalog_mod.RedisCatalogStore)
    assert store._redis is fake_client


def test_default_store_falls_back_when_redis_client_missing(monkeypatch):
    monkeypatch.setattr(catalog_mod, "cache", SimpleNamespace())
    store = catalog_mod._build_default_store()
    assert isinstance(store, catalog_mod.DjangoCacheCatalogStore)


def test_redis_store_get_normalizes_ready_flag_bytes():
    class FakeRedis:
        def __init__(self):
            self.values = {}

        def set(self, key, value, nx=False, ex=None):
            self.values[key] = str(value).encode()
            return True

        def get(self, key):
            return self.values.get(key)

    store = catalog_mod.RedisCatalogStore(FakeRedis())
    store.set("alerts:push_source_ids:ready:v1:1", 1)
    assert store.get("alerts:push_source_ids:ready:v1:1") == 1
    assert store.get("missing") is None


def test_cap_does_not_throttle_rejected_members():
    cat = catalog()
    cat.observe([1], [f"s{i}" for i in range(PushSourceCatalog.MAX_MEMBERS)])
    cat.observe([1], ["overflow", "s0"])
    assert (1, "overflow") not in cat._throttle
    assert (1, "s0") in cat._throttle


@pytest.mark.django_db
def test_rebuild_loads_snapshot_and_marks_ready_even_when_empty():
    now = timezone.now()
    Alert.objects.create(
        alert_id="A1", fingerprint="f1", title="t", content="", level="1", team=[1], push_source_ids=["prod", "001"], last_event_time=now
    )
    Alert.objects.create(alert_id="A2", fingerprint="f2", title="t", content="", level="1", team=[2], push_source_ids=["other"], last_event_time=now)
    Alert.objects.create(
        alert_id="old",
        fingerprint="f3",
        title="t",
        content="",
        level="1",
        team=[1],
        push_source_ids=["stale"],
        last_event_time=now - timedelta(days=91),
    )
    Alert.objects.create(alert_id="empty", fingerprint="f4", title="t", content="", level="1", team=[3], push_source_ids=[], last_event_time=now)
    cat = PushSourceCatalog(store=MemoryCatalogStore(), now=lambda: int(now.timestamp()), min_interval=0)
    assert cat.list_for_teams([1]) == ["001", "prod"]
    assert "stale" not in cat.list_for_teams([1])
    assert cat.list_for_teams([3]) == []
    assert cat.store.get("alerts:push_source_ids:ready:v1:1") == 1
    assert cat.store.get("alerts:push_source_ids:ready:v1:3") == 1


@pytest.mark.django_db
def test_observe_does_not_mark_ready_or_skip_historical_rebuild():
    now = timezone.now()
    Alert.objects.create(
        alert_id="H1",
        fingerprint="fh",
        title="t",
        content="",
        level="1",
        team=[1],
        push_source_ids=["hist"],
        last_event_time=now,
    )
    cat = PushSourceCatalog(store=MemoryCatalogStore(), now=lambda: int(now.timestamp()) + 50, min_interval=0)
    cat.observe([1], ["live"])
    assert cat.store.get("alerts:push_source_ids:ready:v1:1") != 1
    assert set(cat.list_for_teams([1])) >= {"hist", "live"}


@pytest.mark.django_db
def test_rebuild_merges_and_does_not_clobber_live_observe():
    now = timezone.now()
    Alert.objects.create(alert_id="A1", fingerprint="f1", title="t", content="", level="1", team=[1], push_source_ids=["prod"], last_event_time=now)
    cat = PushSourceCatalog(store=MemoryCatalogStore(), now=lambda: int(now.timestamp()) + 50, min_interval=0)
    cat.observe([1], ["live"])
    cat.rebuild_for_team(1)
    assert set(cat.list_for_teams([1])) >= {"prod", "live"}


@pytest.mark.django_db
def test_keep_newest_does_not_clobber_observe_during_rebuild():
    now = 1_700_000_000
    extra = "oldest-extra"
    concurrent_score = now + 10_000

    class ConcurrentDuringKeep(MemoryCatalogStore):
        def zrevrange(self, key, start, end, withscores=False):
            result = super().zrevrange(key, start, end, withscores=withscores)
            if self.zcard(key) > PushSourceCatalog.MAX_MEMBERS:
                self.zadd(key, {"concurrent": concurrent_score})
            return result

    cat = PushSourceCatalog(store=ConcurrentDuringKeep(), now=lambda: now, min_interval=0)
    key = cat.KEY.format(team_id=1)
    seeded = {f"s{i}": now - i for i in range(PushSourceCatalog.MAX_MEMBERS)}
    seeded[extra] = now - PushSourceCatalog.MAX_MEMBERS - 1
    cat.store.zadd(key, seeded)
    cat.rebuild_for_team(1)
    members = cat.list_for_teams([1])
    assert "concurrent" in members
    assert extra not in members
    assert cat.store.zscore(key, extra) is None


@pytest.mark.django_db
def test_list_rebuilds_once_under_lock():
    cat = PushSourceCatalog(store=MemoryCatalogStore(), now=lambda: 1, min_interval=0)
    first = cat.list_for_teams([9])
    second = cat.list_for_teams([9])
    assert first == second == []
    assert cat.store.get("alerts:push_source_ids:ready:v1:9") == 1


def test_rebuild_releases_lock_when_snapshot_mapping_fails():
    cat = catalog()
    calls = {"n": 0}

    def boom(_team_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("mapping failed")
        return {"prod": 1_700_000_000}

    cat._snapshot_mapping = boom
    with pytest.raises(RuntimeError):
        cat.rebuild_for_team(1)
    lock_key = cat.LOCK_KEY.format(team_id=1)
    assert cat.store.get(lock_key) is None
    assert cat.store.add(lock_key, 1) is True
    cat.store.delete(lock_key)
    assert cat.rebuild_for_team(1) == {"prod": 1_700_000_000}
    assert calls["n"] == 2
    assert cat.store.get(lock_key) is None
    assert cat.store.get(cat.READY_KEY.format(team_id=1)) == 1


def test_rebuild_returns_mapping_when_zadd_fails():
    mapping_result = {"fresh": 1_700_000_000}

    class BoomZadd(MemoryCatalogStore):
        def zadd(self, key, mapping):
            raise RuntimeError("zadd failed")

    cat = PushSourceCatalog(store=BoomZadd(), now=lambda: 1_700_000_000, min_interval=0)
    cat._snapshot_mapping = lambda _team_id: dict(mapping_result)
    result = cat.rebuild_for_team(1)
    assert result == mapping_result
    assert cat.store.get(cat.READY_KEY.format(team_id=1)) != 1
    assert cat.store.get(cat.LOCK_KEY.format(team_id=1)) is None
    assert cat.list_for_teams([1]) == ["fresh"]


@pytest.mark.django_db
def test_snapshot_filters_time_window_before_team_scope(monkeypatch):
    captured = {}
    original = catalog_mod.apply_team_scope_with_group_ids

    def capture(qs, team_ids):
        captured["sql"] = str(qs.query.where)
        return original(qs, team_ids)

    monkeypatch.setattr(catalog_mod, "apply_team_scope_with_group_ids", capture)
    cat = catalog()
    cat.rebuild_for_team(1)
    where_sql = captured["sql"].lower()
    assert "last_event_time" in where_sql
    assert "updated_at" in where_sql


def test_observe_accepts_fresh_id_after_stale_set_is_full():
    now = 1_700_000_000
    cat = PushSourceCatalog(store=MemoryCatalogStore(), now=lambda: now, min_interval=0)
    stale_score = now - PushSourceCatalog.STALE_SECONDS - 1
    cat.store.zadd(
        "alerts:push_source_ids:v1:1",
        {f"old{i}": stale_score for i in range(PushSourceCatalog.MAX_MEMBERS)},
    )
    cat.store.set("alerts:push_source_ids:ready:v1:1", 1)
    cat.observe([1], ["fresh"])
    members = cat.list_for_teams([1])
    assert "fresh" in members


def test_list_rebuild_failure_logs_type_without_payload(caplog, capsys):
    sentinel = "snapshot-secret-payload"
    source_sentinel = "prod-secret-id"
    cat = PushSourceCatalog(store=MemoryCatalogStore(), now=lambda: 1, min_interval=0)
    cat.store.zadd("alerts:push_source_ids:v1:1", {source_sentinel: 1})

    def boom(_team_id):
        raise RuntimeError(sentinel)

    cat.rebuild_for_team = boom
    with caplog.at_level(logging.WARNING, logger="alert"):
        assert cat.list_for_teams([1]) == [source_sentinel]
    records = [record for record in caplog.records if record.name == "alert"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.msg == "push source catalog rebuild failed: team_id=%s error_type=%s"
    assert record.args == (1, "RuntimeError")
    assert record.getMessage() == "push source catalog rebuild failed: team_id=1 error_type=RuntimeError"
    assert record.exc_info is None
    output = capsys.readouterr()
    blob = repr(record.args) + logging.Formatter().format(record) + caplog.text + output.out + output.err
    assert sentinel not in blob
    assert source_sentinel not in blob
