"""Elasticsearch 剩余工具：cat/cluster/文档/搜索/快照/mapping/ingest/alias。

删除/restore/bulk/pipeline 必须 confirm=True；失败走 error_type。
"""
from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.tools.elasticsearch import aliases as als
from apps.opspilot.metis.llm.tools.elasticsearch import cat as cat_mod
from apps.opspilot.metis.llm.tools.elasticsearch import cluster as clu
from apps.opspilot.metis.llm.tools.elasticsearch import documents as docs
from apps.opspilot.metis.llm.tools.elasticsearch import ingest as ing
from apps.opspilot.metis.llm.tools.elasticsearch import mappings as maps
from apps.opspilot.metis.llm.tools.elasticsearch import search as sch
from apps.opspilot.metis.llm.tools.elasticsearch import snapshots as snap

pytestmark = pytest.mark.unit


def _client():
    client = MagicMock()
    client.ping.return_value = True
    client.info.return_value = {"cluster_name": "es"}
    client.cluster.health.return_value = {"status": "green"}
    client.cluster.stats.return_value = {"nodes": {"count": 1}}
    client.nodes.info.return_value = {"nodes": {}}
    client.nodes.stats.return_value = {"nodes": {}}
    client.cat.indices.return_value = [{"index": "logs"}]
    client.cat.shards.return_value = [{"index": "logs", "shard": "0"}]
    client.cat.nodes.return_value = [{"name": "n1"}]
    client.cat.aliases.return_value = [{"alias": "logs-write"}]
    client.cat.allocation.return_value = [{"node": "n1"}]
    client.cat.recovery.return_value = []
    client.get.return_value = {"_id": "1", "_source": {"a": 1}}
    client.index.return_value = {"result": "created"}
    client.delete.return_value = {"result": "deleted"}
    client.update.return_value = {"result": "updated"}
    client.mget.return_value = {"docs": [{"_id": "1"}]}
    client.bulk.return_value = {"errors": False}
    client.search.return_value = {"took": 3, "timed_out": False, "hits": {"total": {"value": 1}, "hits": [{"_id": "1"}]}}
    client.count.return_value = {"count": 2}
    client.indices.validate_query.return_value = {"valid": True}
    client.msearch.return_value = {"responses": []}
    client.explain.return_value = {"matched": True}
    client.search_template.return_value = {"hits": {"hits": []}}
    client.snapshot.get_repository.return_value = {"fs": {}}
    client.snapshot.create_repository.return_value = {"acknowledged": True}
    client.snapshot.get.return_value = {"snapshots": []}
    client.snapshot.create.return_value = {"accepted": True}
    client.snapshot.restore.return_value = {"accepted": True}
    client.indices.get_mapping.return_value = {"logs": {"mappings": {}}}
    client.indices.get_settings.return_value = {"logs": {"settings": {}}}
    client.indices.put_mapping.return_value = {"acknowledged": True}
    client.indices.put_settings.return_value = {"acknowledged": True}
    client.field_caps.return_value = {"fields": {}}
    client.indices.get_alias.return_value = {"logs": {"aliases": {"logs-write": {}}}}
    client.indices.exists_alias.return_value = True
    client.indices.update_aliases.return_value = {"acknowledged": True}
    client.ingest.get_pipeline.return_value = {"p1": {}}
    client.ingest.put_pipeline.return_value = {"acknowledged": True}
    client.ingest.delete_pipeline.return_value = {"acknowledged": True}
    client.ingest.simulate.return_value = {"docs": []}
    return client


def test_cluster_ping_info_and_health():
    client = _client()
    with patch.object(clu, "get_es_client", return_value=client):
        ping = clu.es_ping.invoke({})
        assert ping["success"] is True
        assert ping["data"]["pong"] is True
        info = clu.es_info.invoke({})
        assert info["data"]["cluster_name"] == "es"
        health = clu.es_cluster_health.invoke({})
        assert health["data"]["status"] == "green"
        named = clu.es_cluster_health.invoke({"index": "logs"})
        assert named["index"] == "logs"
        client.cluster.health.assert_any_call(index="logs")
        stats = clu.es_cluster_stats.invoke({})
        assert stats["success"] is True
        nodes = clu.es_nodes_info.invoke({})
        assert nodes["success"] is True
        node_stats = clu.es_nodes_stats.invoke({})
        assert node_stats["success"] is True
    with patch.object(clu, "get_es_client", side_effect=RuntimeError("refused")):
        err = clu.es_ping.invoke({})
    assert err["success"] is False
    assert err["error_type"] == "connection_error"


def test_cat_indices_shards_nodes_and_aliases():
    client = _client()
    with patch.object(cat_mod, "get_es_client", return_value=client):
        indices = cat_mod.es_cat_indices.invoke({"index": "logs*"})
        assert indices["success"] is True
        assert indices["data"][0]["index"] == "logs"
        shards = cat_mod.es_cat_shards.invoke({"index": "logs"})
        assert shards["data"][0]["shard"] == "0"
        nodes = cat_mod.es_cat_nodes.invoke({})
        assert nodes["data"][0]["name"] == "n1"
        aliases = cat_mod.es_cat_aliases.invoke({})
        assert aliases["data"][0]["alias"] == "logs-write"
        alloc = cat_mod.es_cat_allocation.invoke({})
        assert alloc["success"] is True
        recovery = cat_mod.es_cat_recovery.invoke({})
        assert recovery["data"] == []
    with patch.object(cat_mod, "get_es_client", side_effect=RuntimeError("down")):
        err = cat_mod.es_cat_nodes.invoke({})
    assert err["success"] is False


def test_documents_crud_and_confirm_guards():
    denied = docs.es_delete_document.invoke({"index": "logs", "doc_id": "1", "confirm": False})
    assert denied["error_type"] == "confirmation_required"
    denied_bulk = docs.es_bulk.invoke({"operations": [], "confirm": False})
    assert denied_bulk["error_type"] == "confirmation_required"
    client = _client()
    with patch.object(docs, "get_es_client", return_value=client):
        got = docs.es_get_document.invoke({"index": "logs", "doc_id": "1"})
        assert got["data"]["_id"] == "1"
        indexed = docs.es_index_document.invoke({"index": "logs", "document": {"a": 1}, "doc_id": "1"})
        assert indexed["success"] is True
        deleted = docs.es_delete_document.invoke({"index": "logs", "doc_id": "1", "confirm": True})
        assert deleted["success"] is True
        updated = docs.es_update_document.invoke({"index": "logs", "doc_id": "1", "doc": {"a": 2}})
        assert updated["success"] is True
        mget = docs.es_multi_get.invoke({"index": "logs", "ids": ["1"]})
        assert mget["data"]["docs"][0]["_id"] == "1"
        bulk = docs.es_bulk.invoke({"operations": [{"index": {}}], "confirm": True})
        assert bulk["success"] is True
    with patch.object(docs, "get_es_client", side_effect=RuntimeError("missing")):
        err = docs.es_get_document.invoke({"index": "logs", "doc_id": "x"})
    assert err["error_type"] == "not_found"


def test_search_count_validate_and_knn():
    client = _client()
    with patch.object(sch, "get_es_client", return_value=client):
        searched = sch.es_search.invoke({"index": "logs", "query": {"match_all": {}}})
        assert searched["data"]["total"] == 1
        assert searched["data"]["hits"][0]["_id"] == "1"
        counted = sch.es_count.invoke({"index": "logs"})
        assert counted["data"]["count"] == 2
        valid = sch.es_validate_query.invoke({"index": "logs", "query": {"match_all": {}}})
        assert valid["data"]["valid"] is True
        msearch = sch.es_multi_search.invoke({"searches": [{}, {}]})
        assert msearch["success"] is True
        explained = sch.es_explain.invoke({"index": "logs", "doc_id": "1", "query": {"match_all": {}}})
        assert explained["data"]["matched"] is True
        templated = sch.es_search_template.invoke({"index": "logs", "source": {"query": {"match_all": {}}}})
        assert templated["success"] is True
        knn = sch.es_knn_search.invoke({"index": "logs", "knn": {"field": "vec", "query_vector": [0.1], "k": 1}})
        assert knn["success"] is True
    with patch.object(sch, "get_es_client", side_effect=RuntimeError("bad query")):
        err = sch.es_search.invoke({"index": "logs", "query": {}})
    assert err["success"] is False


def test_snapshots_restore_requires_confirm():
    denied = snap.es_restore_snapshot.invoke({"repository": "fs", "snapshot": "s1", "confirm": False})
    assert denied["error_type"] == "confirmation_required"
    client = _client()
    with patch.object(snap, "get_es_client", return_value=client):
        repos = snap.es_get_snapshot_repositories.invoke({})
        assert "fs" in repos["data"]
        created_repo = snap.es_create_snapshot_repository.invoke({"repository": "fs", "body": {"type": "fs"}})
        assert created_repo["success"] is True
        listed = snap.es_get_snapshots.invoke({"repository": "fs"})
        assert listed["success"] is True
        created = snap.es_create_snapshot.invoke({"repository": "fs", "snapshot": "s1"})
        assert created["success"] is True
        restored = snap.es_restore_snapshot.invoke({"repository": "fs", "snapshot": "s1", "confirm": True})
        assert restored["success"] is True
        client.snapshot.restore.assert_called_once()
    with patch.object(snap, "get_es_client", side_effect=RuntimeError("no repo")):
        err = snap.es_get_snapshots.invoke({"repository": "missing"})
    assert err["success"] is False


def test_mappings_settings_and_aliases():
    client = _client()
    with patch.object(maps, "get_es_client", return_value=client):
        mapping = maps.es_get_mapping.invoke({"index": "logs"})
        assert mapping["success"] is True
        settings = maps.es_get_settings.invoke({"index": "logs"})
        assert settings["success"] is True
        put_map = maps.es_put_mapping.invoke({"index": "logs", "body": {"properties": {"a": {"type": "keyword"}}}})
        assert put_map["success"] is True
        put_set = maps.es_put_settings.invoke({"index": "logs", "body": {"index": {"number_of_replicas": 0}}})
        assert put_set["success"] is True
        caps = maps.es_field_caps.invoke({"index": "logs", "fields": ["a"]})
        assert caps["success"] is True
    with patch.object(als, "get_es_client", return_value=client):
        alias = als.es_get_alias.invoke({"name": "logs-write"})
        assert alias["success"] is True
        exists = als.es_alias_exists.invoke({"name": "logs-write"})
        assert exists["data"]["exists"] is True
        updated = als.es_update_aliases.invoke({"actions": [{"add": {"index": "logs", "alias": "logs-write"}}]})
        assert updated["success"] is True


def test_ingest_pipeline_delete_requires_confirm():
    denied = ing.es_delete_pipeline.invoke({"pipeline_id": "p1", "confirm": False})
    assert denied["error_type"] == "confirmation_required"
    client = _client()
    with patch.object(ing, "get_es_client", return_value=client):
        got = ing.es_get_pipeline.invoke({"pipeline_id": "p1"})
        assert got["success"] is True
        put = ing.es_put_pipeline.invoke({"pipeline_id": "p1", "body": {"processors": []}})
        assert put["success"] is True
        deleted = ing.es_delete_pipeline.invoke({"pipeline_id": "p1", "confirm": True})
        assert deleted["success"] is True
        simulated = ing.es_simulate_pipeline.invoke({"body": {"docs": []}, "pipeline_id": "p1"})
        assert simulated["success"] is True
    with patch.object(ing, "get_es_client", side_effect=RuntimeError("gone")):
        err = ing.es_get_pipeline.invoke({"pipeline_id": "missing"})
    assert err["success"] is False
