"""PostgreSQL 资源/优化工具：数据库信息、列表、未用索引浪费空间。"""
import json
from unittest.mock import patch

import pytest

from apps.opspilot.metis.llm.tools.postgres import optimization as opt
from apps.opspilot.metis.llm.tools.postgres import resources as res

pytestmark = pytest.mark.unit
CONFIG = {"configurable": {"host": "127.0.0.1"}}


def test_current_database_info_and_error():
    row = {
        "database_name": "app",
        "username": "u",
        "pg_version": "PostgreSQL 15.4",
        "current_schema": "public",
        "search_path": "public",
    }
    with patch.object(res, "execute_readonly_query", return_value=[row]):
        out = json.loads(res.get_current_database_info.invoke({"config": CONFIG}))
    assert out["current_database"] == "app"
    assert "15.4" in out["postgres_version"]
    with patch.object(res, "execute_readonly_query", side_effect=RuntimeError("denied")):
        err = json.loads(res.get_current_database_info.invoke({"config": CONFIG}))
    assert "denied" in err["error"]


def test_list_postgres_databases_formats_size():
    rows = [{"name": "app", "size_bytes": 2048, "connections": 3, "owner": "u", "encoding": "UTF8", "collate": "C"}]
    with patch.object(res, "execute_readonly_query", return_value=rows):
        out = json.loads(res.list_postgres_databases.invoke({"config": CONFIG}))
    assert out["total_databases"] == 1
    assert out["databases"][0]["size"] == "2.00 KB"


def test_check_unused_indexes_sums_wasted_space():
    rows = [
        {"index_name": "idx_dead", "index_size_bytes": 1024 * 1024, "index_scans": 0, "table_name": "t"},
    ]
    with patch.object(opt, "execute_readonly_query", return_value=rows):
        out = json.loads(opt.check_unused_indexes.invoke({"size_threshold_mb": 1, "config": CONFIG}))
    assert out["unused_index_count"] == 1
    assert out["total_wasted_bytes"] == 1024 * 1024
    assert out["recommendations"][0] == "考虑删除1个未使用的索引,可节省1.00 MB"
    with patch.object(opt, "execute_readonly_query", return_value=[]):
        empty = json.loads(opt.check_unused_indexes.invoke({"config": CONFIG}))
    assert empty["unused_index_count"] == 0
    assert "未发现" in empty["recommendations"][0]
