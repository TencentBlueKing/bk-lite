"""Elasticsearch 索引工具剩余：refresh/stats/forcemerge 成功，以及客户端异常走 es_error。"""
from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.tools.elasticsearch import indices as idx

pytestmark = pytest.mark.unit


def test_refresh_stats_and_forcemerge_success():
    client = MagicMock()
    client.indices.refresh.return_value = {"_shards": {"successful": 1}}
    client.indices.stats.return_value = {"indices": {"logs": {}}}
    client.indices.forcemerge.return_value = {"_shards": {"successful": 1}}
    with patch.object(idx, "get_es_client", return_value=client):
        refreshed = idx.es_refresh_index.invoke({"index": "logs"})
        stats = idx.es_index_stats.invoke({"index": "logs"})
        merged = idx.es_forcemerge_index.invoke({"index": "logs", "max_num_segments": 1, "confirm": True})
    assert refreshed == {"success": True, "data": {"_shards": {"successful": 1}}, "index": "logs"}
    assert stats["success"] is True
    assert stats["index"] == "logs"
    assert merged["success"] is True
    client.indices.forcemerge.assert_called_once_with(index="logs", max_num_segments=1)


def test_forcemerge_and_close_require_confirm():
    denied_merge = idx.es_forcemerge_index.invoke({"index": "logs", "confirm": False})
    assert denied_merge == {
        "success": False,
        "error": "Operation 'forcemerge_index' requires confirm=True",
        "error_type": "confirmation_required",
    }
    denied_close = idx.es_close_index.invoke({"index": "logs", "confirm": False})
    assert denied_close["error_type"] == "confirmation_required"


def test_list_exists_create_open_close_delete_wrap_client_errors():
    with patch.object(idx, "get_es_client", side_effect=RuntimeError("cluster down")):
        listed = idx.es_list_indices.invoke({})
        exists = idx.es_index_exists.invoke({"index": "logs"})
        created = idx.es_create_index.invoke({"index": "new"})
        opened = idx.es_open_index.invoke({"index": "logs"})
        refreshed = idx.es_refresh_index.invoke({"index": "logs"})
        stats = idx.es_index_stats.invoke({"index": "logs"})
        deleted = idx.es_delete_index.invoke({"index": "logs", "confirm": True})
        closed = idx.es_close_index.invoke({"index": "logs", "confirm": True})
        merged = idx.es_forcemerge_index.invoke({"index": "logs", "confirm": True})
    for err in (listed, exists, created, opened, refreshed, stats, deleted, closed, merged):
        assert err == {"success": False, "error": "cluster down", "error_type": "es_error"}
