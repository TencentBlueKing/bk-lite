import logging
from types import SimpleNamespace

import pytest

from apps.alerts.service import push_source_catalog as catalog_mod
from apps.alerts.service.push_source_catalog import MemoryCatalogStore, PushSourceCatalog

pytestmark = [pytest.mark.unit]


def catalog():
    return PushSourceCatalog(store=MemoryCatalogStore(), now=lambda: 1_700_000_000, min_interval=60)


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
