import json
import logging
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.cmdb.display_field import cache as cache_mod
from apps.cmdb.display_field.cache import ExcludeFieldsCache
from apps.core.logger import SafeLogException

pytestmark = pytest.mark.unit


class MemoryCache:
    def __init__(self):
        self.values = {}
        self.fail_get = False
        self.fail_set = False

    def get(self, key):
        if self.fail_get:
            raise RuntimeError("cache read failed")
        return self.values.get(key)

    def set(self, key, value, timeout=None):
        if self.fail_set:
            raise RuntimeError("cache write failed")
        self.values[key] = value
        return True

    def delete(self, key):
        self.values.pop(key, None)
        return True

    def delete_many(self, keys):
        for key in keys:
            self.values.pop(key, None)
        return len(keys)


class GraphStub:
    def __init__(self, models=None, error=None):
        self.models = models or []
        self.error = error
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def query_entity(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.models, len(self.models)

    def set_entity_properties(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return []


@pytest.fixture
def memory_cache(monkeypatch):
    backend = MemoryCache()
    monkeypatch.setattr(cache_mod, "cache", backend)
    return backend


def test_cmdb_ready_has_no_field_cache_side_effect(monkeypatch):
    import apps.cmdb as cmdb_module
    from apps.cmdb.apps import CmdbConfig

    calls = []
    monkeypatch.setattr(ExcludeFieldsCache, "refresh_cache", classmethod(lambda cls: calls.append("refresh")))

    CmdbConfig("apps.cmdb", cmdb_module).ready()

    assert calls == []


def test_global_cache_miss_builds_one_snapshot_without_warming_model_attrs(monkeypatch, memory_cache):
    models = [
        {
            "model_id": "host",
            "attrs": json.dumps(
                [
                    {"attr_id": "organization", "attr_type": "organization"},
                    {"attr_id": "manager", "attr_type": "user"},
                    {"attr_id": "name", "attr_type": "str"},
                ]
            ),
        }
    ]
    graph = GraphStub(models)
    monkeypatch.setattr(cache_mod, "GraphClient", lambda: graph)

    assert ExcludeFieldsCache.get_exclude_fields() == ["manager", "organization"]
    assert ExcludeFieldsCache.get_model_fields_mapping() == {"host": {"organization": ["organization"], "user": ["manager"]}}
    assert len(graph.calls) == 1
    assert not any(key.startswith(ExcludeFieldsCache.MODEL_ATTRS_KEY_PREFIX) for key in memory_cache.values)


def test_global_cache_load_failure_does_not_publish_empty_snapshot(monkeypatch, memory_cache):
    monkeypatch.setattr(cache_mod, "GraphClient", lambda: GraphStub(error=RuntimeError("graph unavailable")))

    with pytest.raises(RuntimeError, match="graph unavailable"):
        ExcludeFieldsCache.get_exclude_fields()

    assert ExcludeFieldsCache.FIELD_METADATA_KEY not in memory_cache.values


def test_malformed_model_attrs_do_not_publish_partial_snapshot(monkeypatch, memory_cache):
    models = [
        {"model_id": "broken", "attrs": "not-json"},
        {"model_id": "host", "attrs": json.dumps([{"attr_id": "org", "attr_type": "organization"}])},
    ]
    monkeypatch.setattr(cache_mod, "GraphClient", lambda: GraphStub(models))

    with pytest.raises(json.JSONDecodeError):
        ExcludeFieldsCache.get_model_fields_mapping()

    assert ExcludeFieldsCache.FIELD_METADATA_KEY not in memory_cache.values


def test_cache_write_failure_returns_fresh_global_data(monkeypatch, memory_cache):
    models = [{"model_id": "host", "attrs": json.dumps([{"attr_id": "org", "attr_type": "organization"}])}]
    monkeypatch.setattr(cache_mod, "GraphClient", lambda: GraphStub(models))
    memory_cache.fail_set = True

    assert ExcludeFieldsCache.get_exclude_fields() == ["org"]


def test_cache_read_failure_falls_back_to_model_source(monkeypatch, memory_cache):
    models = [{"model_id": "host", "attrs": json.dumps([{"attr_id": "name", "attr_type": "str"}])}]
    graph = GraphStub(models)
    monkeypatch.setattr(cache_mod, "GraphClient", lambda: graph)
    memory_cache.fail_get = True

    assert ExcludeFieldsCache.get_exclude_fields() == []
    assert len(graph.calls) == 1


def test_model_attrs_load_failure_is_not_converted_to_empty(monkeypatch, memory_cache):
    def raise_source_error(*args, **kwargs):
        raise RuntimeError("model attrs unavailable")

    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr", staticmethod(raise_source_error))

    with pytest.raises(RuntimeError, match="model attrs unavailable"):
        ExcludeFieldsCache.get_model_attrs("host")

    assert f"{ExcludeFieldsCache.MODEL_ATTRS_KEY_PREFIX}host" not in memory_cache.values


def test_model_attrs_cache_write_failure_returns_fresh_data(monkeypatch, memory_cache):
    attrs = [{"attr_id": "name", "unique_display_type": "single"}]
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr", staticmethod(lambda *args, **kwargs: attrs))
    memory_cache.fail_set = True

    assert ExcludeFieldsCache.get_model_attrs("host") == attrs


def test_model_schema_change_invalidates_target_attrs_and_global_snapshot(memory_cache):
    target_key = f"{ExcludeFieldsCache.MODEL_ATTRS_KEY_PREFIX}host"
    other_key = f"{ExcludeFieldsCache.MODEL_ATTRS_KEY_PREFIX}switch"
    memory_cache.values.update(
        {
            target_key: [{"stale": True}],
            other_key: [{"stale": True}],
            ExcludeFieldsCache.FIELD_METADATA_KEY: {"exclude_fields": ["old"], "model_fields_mapping": {}},
        }
    )

    assert ExcludeFieldsCache.update_on_model_change("host") is True

    assert target_key not in memory_cache.values
    assert ExcludeFieldsCache.FIELD_METADATA_KEY not in memory_cache.values
    assert memory_cache.values[other_key] == [{"stale": True}]


def test_attrs_only_change_keeps_global_snapshot(memory_cache):
    target_key = f"{ExcludeFieldsCache.MODEL_ATTRS_KEY_PREFIX}host"
    snapshot = {"exclude_fields": ["organization"], "model_fields_mapping": {}}
    memory_cache.values.update({target_key: [{"stale": True}], ExcludeFieldsCache.FIELD_METADATA_KEY: snapshot})

    assert ExcludeFieldsCache.invalidate_model_attrs("host") is True

    assert target_key not in memory_cache.values
    assert memory_cache.values[ExcludeFieldsCache.FIELD_METADATA_KEY] == snapshot


def test_unique_rule_write_invalidates_model_attrs(monkeypatch):
    from apps.cmdb.services import unique_rule

    invalidated = []
    graph = GraphStub()
    monkeypatch.setattr(unique_rule, "search_model_info", lambda model_id: {"_id": 7})
    monkeypatch.setattr("apps.cmdb.graph.drivers.graph_client.GraphClient", lambda: graph)
    monkeypatch.setattr(ExcludeFieldsCache, "invalidate_model_attrs", lambda model_id: invalidated.append(model_id))

    unique_rule._save_unique_rules("host", [])

    assert invalidated == ["host"]
    assert len(graph.calls) == 1


def test_tag_option_write_invalidates_model_attrs(monkeypatch):
    attrs = [
        {
            "attr_id": "tag",
            "attr_type": "tag",
            "option": {"mode": "free", "options": []},
        }
    ]
    graph = GraphStub()
    invalidated = []
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        staticmethod(lambda model_id: {"_id": 7, "attrs": json.dumps(attrs)}),
    )
    monkeypatch.setattr("apps.cmdb.services.model.GraphClient", lambda: graph)
    monkeypatch.setattr(ExcludeFieldsCache, "invalidate_model_attrs", lambda model_id: invalidated.append(model_id))

    from apps.cmdb.services.model import ModelManage

    ModelManage.merge_tag_options_from_values("host", ["env:prod"])

    assert invalidated == ["host"]
    assert len(graph.calls) == 1


def test_failed_manual_refresh_preserves_existing_snapshot_and_safe_log(monkeypatch, memory_cache, caplog):
    sensitive_sentinel = "cache-password-secret-9f3a"
    snapshot = {"exclude_fields": ["organization"], "model_fields_mapping": {}}
    memory_cache.values[ExcludeFieldsCache.FIELD_METADATA_KEY] = snapshot
    source_error = RuntimeError(sensitive_sentinel)
    monkeypatch.setattr(cache_mod, "GraphClient", lambda: GraphStub(error=source_error))

    with caplog.at_level(logging.ERROR, logger="cmdb"):
        assert ExcludeFieldsCache.refresh_cache() is False
    assert memory_cache.values[ExcludeFieldsCache.FIELD_METADATA_KEY] == snapshot

    records = [record for record in caplog.records if record.getMessage().startswith("event=cmdb_field_metadata_cache_refresh_failed")]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=cmdb_field_metadata_cache_refresh_failed failed_stage=%s error_type=%s call_chain=%s"
    assert record.args[0:2] == ("load_model_metadata", "RuntimeError")
    assert sensitive_sentinel not in logging.Formatter("%(message)s").format(record)
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[2] is source_error.__traceback__


def test_clear_cache_removes_global_and_indexed_model_entries(monkeypatch, memory_cache):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr",
        staticmethod(lambda model_id, *args, **kwargs: [{"attr_id": model_id}]),
    )
    ExcludeFieldsCache.get_model_attrs("host")
    ExcludeFieldsCache.get_model_attrs("switch")
    memory_cache.values[ExcludeFieldsCache.FIELD_METADATA_KEY] = {"exclude_fields": [], "model_fields_mapping": {}}

    assert ExcludeFieldsCache.clear_cache() is True

    assert ExcludeFieldsCache.FIELD_METADATA_KEY not in memory_cache.values
    assert f"{ExcludeFieldsCache.MODEL_ATTRS_KEY_PREFIX}host" not in memory_cache.values
    assert f"{ExcludeFieldsCache.MODEL_ATTRS_KEY_PREFIX}switch" not in memory_cache.values


def test_refresh_cache_command_selects_global_or_model_scope(monkeypatch):
    calls = []
    monkeypatch.setattr(ExcludeFieldsCache, "refresh_cache", classmethod(lambda cls: calls.append("global") or True))
    monkeypatch.setattr(
        ExcludeFieldsCache,
        "refresh_model_attrs",
        classmethod(lambda cls, model_id: calls.append(("model", model_id)) or True),
    )

    output = StringIO()
    call_command("refresh_cmdb_field_cache", stdout=output)
    call_command("refresh_cmdb_field_cache", model_id="host", stdout=output)

    assert calls == ["global", ("model", "host")]


def test_refresh_cache_command_reports_failure(monkeypatch):
    monkeypatch.setattr(ExcludeFieldsCache, "refresh_cache", classmethod(lambda cls: False))

    with pytest.raises(CommandError, match="刷新 CMDB 字段元数据缓存失败"):
        call_command("refresh_cmdb_field_cache")
