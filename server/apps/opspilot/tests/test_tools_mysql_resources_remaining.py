"""MySQL 资源工具剩余：uptime 未知、外层 Error 包装。"""
import json
from unittest.mock import patch

import pytest
from mysql.connector import Error

from apps.opspilot.metis.llm.tools.mysql import resources as res

pytestmark = pytest.mark.unit

NORMALIZED = {
    "mode": "single",
    "legacy_single": True,
    "items": [{"index": 0, "name": "db1", "raw": {}, "config": {"database": "app"}}],
}


class FakeConn:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_current_database_info_uptime_unknown_and_outer_error():
    conn = FakeConn()
    info = {
        "version": "8.0",
        "hostname": "h",
        "port": 3306,
        "datadir": "/var/lib/mysql",
        "character_set_server": "utf8mb4",
        "collation_server": "utf8mb4_bin",
        "default_storage_engine": "InnoDB",
    }
    with (
        patch.object(res, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
        patch.object(res, "get_mysql_connection_from_item", return_value=conn),
        patch.object(res, "execute_readonly_query", side_effect=[[info], Error("no pfs")]),
    ):
        out = json.loads(res.get_current_database_info.invoke({"config": {"configurable": {}}}))
    assert out["version"] == "8.0"
    assert out["uptime_seconds"] == "unknown"
    assert conn.closed is True

    conn = FakeConn()
    with (
        patch.object(res, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
        patch.object(res, "get_mysql_connection_from_item", return_value=conn),
        patch.object(res, "execute_readonly_query", side_effect=Error("gone")),
    ):
        out = json.loads(res.get_current_database_info.invoke({"config": {"configurable": {}}}))
    assert out == {"error": "gone"}
    assert conn.closed is True


def test_remaining_resource_tools_wrap_connector_error():
    conn = FakeConn()
    err = Error("gone")
    cases = [
        (res.list_mysql_databases, {}),
        (res.list_mysql_tables, {"database": "app"}),
        (res.list_mysql_indexes, {"database": "app", "table_name": "hosts"}),
        (res.list_mysql_schemas, {}),
        (res.get_table_structure, {"database": "app", "table_name": "hosts"}),
        (res.list_mysql_users, {}),
    ]
    for tool, extra in cases:
        with (
            patch.object(res, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
            patch.object(res, "get_mysql_connection_from_item", return_value=conn),
            patch.object(res, "execute_readonly_query", side_effect=err),
        ):
            out = json.loads(tool.invoke({"config": {"configurable": {}}, **extra}))
        assert out == {"error": "gone"}
    assert conn.closed is True

    conn = FakeConn()
    with (
        patch.object(res, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
        patch.object(res, "get_mysql_connection_from_item", return_value=conn),
        patch.object(res, "execute_readonly_query", side_effect=err),
    ):
        out = json.loads(res.get_database_config.invoke({"config": {"configurable": {}}}))
    assert out["total_settings"] == 10
    assert out["settings"]["innodb_buffer_pool_size"] == {"value": None}
    assert conn.closed is True
