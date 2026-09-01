"""MySQL 监控剩余：binlog/复制/进程列表/库容量与连接错误包装。"""
import json
from unittest.mock import patch

import pytest
from mysql.connector import Error

from apps.opspilot.metis.llm.tools.mysql import monitoring as mon
from apps.opspilot.metis.llm.tools.mysql.utils import format_size

pytestmark = pytest.mark.unit

NORMALIZED = {
    "mode": "single",
    "legacy_single": True,
    "items": [{"index": 0, "name": "db1", "raw": {}, "config": {"database": "app"}}],
}


class FakeCursor:
    def __init__(self, *, rows=None, fetchones=None, fail_on=None):
        self._rows = rows or []
        self._fetchones = list(fetchones or [])
        self._fail_on = fail_on or {}
        self.last_sql = ""

    def execute(self, sql, params=None):
        self.last_sql = sql
        for needle, exc in self._fail_on.items():
            if needle in sql:
                raise exc
        return None

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._fetchones.pop(0) if self._fetchones else None

    def close(self):
        return None


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self, dictionary=False):
        return self._cursor

    def close(self):
        self.closed = True


def _run(tool, conn, **kwargs):
    with (
        patch.object(mon, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
        patch.object(mon, "get_mysql_connection_from_item", return_value=conn),
    ):
        return json.loads(tool.invoke({"config": {"configurable": {}}, **kwargs}))


def test_database_metrics_wraps_connector_error():
    conn = FakeConn(FakeCursor())
    with (
        patch.object(mon, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
        patch.object(mon, "get_mysql_connection_from_item", return_value=conn),
        patch.object(FakeCursor, "execute", side_effect=Error("gone")),
    ):
        out = json.loads(mon.get_database_metrics.invoke({"config": {"configurable": {}}}))
    assert out == {"error": "gone"}
    assert conn.closed is True


def test_binary_log_on_lists_files_and_swallows_show_binary_logs_error():
    cursor = FakeCursor(
        fetchones=[("log_bin", "ON"), ("binlog_format", "ROW"), ("expire_logs_days", "7"), ("binlog_expire_logs_seconds", "0")],
        rows=[("bin.0001", 2048)],
    )
    out = _run(mon.check_binary_log_status, FakeConn(cursor))
    assert out["log_bin"] == "ON"
    assert out["binlog_format"] == "ROW"
    assert out["binlog_file_count"] == 1
    assert out["binlog_files"][0]["file_size"] == format_size(2048)
    assert out["total_binlog_size"] == format_size(2048)

    cursor = FakeCursor(
        fetchones=[("log_bin", "ON"), ("binlog_format", "ROW"), ("expire_logs_days", "7"), ("binlog_expire_logs_seconds", "0")],
        fail_on={"SHOW BINARY LOGS": Error("no binlog")},
    )
    out = _run(mon.check_binary_log_status, FakeConn(cursor))
    assert out["binlog_files"] == []
    assert out["binlog_file_count"] == 0


def test_replication_falls_back_to_slave_status_and_unconfigured():
    replica = {
        "Source_Host": "10.0.0.2",
        "Source_Port": 3306,
        "Replica_IO_Running": "Yes",
        "Replica_SQL_Running": "Yes",
        "Seconds_Behind_Source": 3,
        "Retrieved_Gtid_Set": "a:1",
        "Executed_Gtid_Set": "a:1",
        "Last_IO_Error": "",
        "Last_SQL_Error": "",
        "Relay_Log_Space": 1024,
    }
    cursor = FakeCursor(fail_on={"SHOW REPLICA STATUS": Error("old mysql")}, fetchones=[replica])
    # fetchone used after fallback execute; FakeCursor.fetchone pops fetchones regardless of SQL.
    out = _run(mon.check_replication_status, FakeConn(cursor))
    assert out["replication_configured"] is True
    assert out["source_host"] == "10.0.0.2"
    assert out["seconds_behind_source"] == 3
    assert out["relay_log_space"] == format_size(1024)

    cursor = FakeCursor(fetchones=[None])
    out = _run(mon.check_replication_status, FakeConn(cursor))
    assert out == {"replication_configured": False, "message": "未配置复制"}


def test_processlist_skips_sleep_without_info():
    cursor = FakeCursor(
        rows=[
            {"Id": 1, "User": "app", "Host": "h", "db": "app", "Command": "Query", "Time": 2, "State": "exec", "Info": "SELECT 1"},
            {"Id": 2, "User": "app", "Host": "h", "db": "app", "Command": "Sleep", "Time": 10, "State": "", "Info": None},
        ]
    )
    out = _run(mon.get_processlist, FakeConn(cursor))
    assert out["active_process_count"] == 1
    assert out["processes"][0]["id"] == 1


def test_database_size_growth_summarizes_and_details():
    summary = [{"TABLE_SCHEMA": "app", "table_count": 2, "data_length": 1024, "index_length": 512, "total_size": 1536}]
    details = [{"TABLE_NAME": "hosts", "DATA_LENGTH": 1024, "INDEX_LENGTH": 512, "total_size": 1536}]
    conn = FakeConn(FakeCursor())
    with (
        patch.object(mon, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
        patch.object(mon, "get_mysql_connection_from_item", return_value=conn),
        patch.object(mon, "execute_readonly_query", side_effect=[summary, details]),
    ):
        out = json.loads(mon.check_database_size_growth.invoke({"database": "app", "config": {"configurable": {}}}))
    assert out["databases"][0]["database"] == "app"
    assert out["database_detail"]["tables"][0]["table_name"] == "hosts"
    assert conn.closed is True


def test_remaining_tools_wrap_connector_error():
    conn = FakeConn(FakeCursor())
    err = Error("gone")
    cases = [
        (mon.get_table_metrics, {"database": "app"}),
        (mon.get_innodb_stats, {}),
        (mon.get_io_stats, {}),
        (mon.check_binary_log_status, {}),
        (mon.check_replication_status, {}),
        (mon.get_processlist, {}),
    ]
    for tool, extra in cases:
        with (
            patch.object(mon, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
            patch.object(mon, "get_mysql_connection_from_item", return_value=conn),
            patch.object(FakeCursor, "execute", side_effect=err),
        ):
            out = json.loads(tool.invoke({"config": {"configurable": {}}, **extra}))
        assert out == {"error": "gone"}

    with (
        patch.object(mon, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
        patch.object(mon, "get_mysql_connection_from_item", return_value=conn),
        patch.object(mon, "execute_readonly_query", side_effect=err),
    ):
        out = json.loads(mon.check_database_size_growth.invoke({"config": {"configurable": {}}}))
    assert out == {"error": "gone"}
    assert conn.closed is True
