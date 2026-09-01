"""Elasticsearch 索引工具：列出/存在性、删除必须 confirm。"""
from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.tools.elasticsearch import indices as idx

pytestmark = pytest.mark.unit


def _client():
    client = MagicMock()
    client.indices.get_alias.return_value = {"logs": {}}
    client.indices.get.return_value = {"logs": {"settings": {}}}
    client.indices.exists.return_value = True
    client.indices.create.return_value = {"acknowledged": True}
    client.indices.delete.return_value = {"acknowledged": True}
    client.indices.open.return_value = {"acknowledged": True}
    client.indices.close.return_value = {"acknowledged": True}
    return client


def test_list_get_exists_and_create_index():
    client = _client()
    with patch.object(idx, "get_es_client", return_value=client):
        listed = idx.es_list_indices.invoke({})
        assert listed["success"] is True
        assert "logs" in listed["data"]
        got = idx.es_get_index.invoke({"index": "logs"})
        assert got["success"] is True
        exists = idx.es_index_exists.invoke({"index": "logs"})
        assert exists["data"]["exists"] is True
        created = idx.es_create_index.invoke({"index": "new"})
        assert created["success"] is True
        client.indices.create.assert_called_once()
    with patch.object(idx, "get_es_client", side_effect=RuntimeError("down")):
        err = idx.es_get_index.invoke({"index": "x"})
    assert err == {"success": False, "error": "down", "error_type": "not_found"}


def test_delete_and_close_require_confirm():
    denied = idx.es_delete_index.invoke({"index": "logs", "confirm": False})
    assert denied["success"] is False
    client = _client()
    with patch.object(idx, "get_es_client", return_value=client):
        ok = idx.es_delete_index.invoke({"index": "logs", "confirm": True})
    assert ok["success"] is True
    client.indices.delete.assert_called_once()
    denied_close = idx.es_close_index.invoke({"index": "logs", "confirm": False})
    assert denied_close["success"] is False
    with patch.object(idx, "get_es_client", return_value=client):
        opened = idx.es_open_index.invoke({"index": "logs"})
    assert opened["success"] is True
