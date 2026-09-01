"""MySQL 监控工具：mock 连接与 SHOW GLOBAL STATUS，断言 QPS/TPS。"""
import json
from unittest.mock import patch

import pytest

from apps.opspilot.metis.llm.tools.mysql import monitoring as mon
from apps.opspilot.metis.llm.tools.mysql.utils import calculate_percentage, format_duration, format_size

pytestmark = pytest.mark.unit

NORMALIZED = {
    "mode": "single",
    "legacy_single": True,
    "items": [{"index": 0, "name": "db1", "raw": {}, "config": {}}],
}


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, sql, params=None):
        return None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        return None


class FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.closed = False

    def cursor(self):
        return FakeCursor(self._rows)

    def close(self):
        self.closed = True


def test_get_database_metrics_computes_qps_tps():
    rows = [
        ("Questions", "100"),
        ("Com_select", "80"),
        ("Com_insert", "10"),
        ("Com_update", "5"),
        ("Com_delete", "5"),
        ("Threads_connected", "3"),
        ("Threads_running", "1"),
        ("Uptime", "10"),
        ("Bytes_received", "2048"),
        ("Bytes_sent", "4096"),
        ("Slow_queries", "2"),
    ]
    conn = FakeConn(rows)
    with (
        patch.object(mon, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
        patch.object(mon, "get_mysql_connection_from_item", return_value=conn),
    ):
        out = json.loads(mon.get_database_metrics.invoke({"config": {"configurable": {}}}))
    assert out["QPS"] == 10.0
    assert out["TPS"] == 2.0
    assert out["Bytes_received_formatted"] == format_size(2048)
    assert out["Bytes_received_formatted"] == "2.00 KB"
    assert out["Bytes_sent_formatted"] == format_size(4096)
    assert out["Bytes_sent_formatted"] == "4.00 KB"
    assert conn.closed is True


def test_get_table_metrics_formats_fragmentation():
    rows = [
        {
            "TABLE_NAME": "hosts",
            "ENGINE": "InnoDB",
            "TABLE_ROWS": 100,
            "DATA_LENGTH": 1024,
            "INDEX_LENGTH": 512,
            "DATA_FREE": 256,
            "AUTO_INCREMENT": 10,
            "CREATE_TIME": None,
            "UPDATE_TIME": None,
        }
    ]
    conn = FakeConn([])
    with (
        patch.object(
            mon,
            "build_mysql_normalized_from_runnable",
            return_value={**NORMALIZED, "items": [{**NORMALIZED["items"][0], "config": {"database": "app"}}]},
        ),
        patch.object(mon, "get_mysql_connection_from_item", return_value=conn),
        patch.object(mon, "execute_readonly_query", return_value=rows),
    ):
        out = json.loads(mon.get_table_metrics.invoke({"config": {"configurable": {}}}))
    assert out["database"] == "app"
    assert out["table_count"] == 1
    table = out["tables"][0]
    assert table["table_name"] == "hosts"
    assert table["data_length"] == format_size(1024)
    assert table["data_length"] == "1.00 KB"
    assert table["index_length"] == format_size(512)
    assert table["index_length"] == "512.00 B"
    assert table["total_size"] == format_size(1536)
    assert table["total_size"] == "1.50 KB"
    assert table["data_free"] == format_size(256)
    assert table["data_free"] == "256.00 B"
    expected_frag = f"{calculate_percentage(256, 1536)}%"
    assert table["fragmentation_ratio"] == expected_frag
    assert table["fragmentation_ratio"] == "16.67%"
    assert conn.closed is True


def test_get_innodb_stats_hit_ratio():
    rows = [
        ("Innodb_buffer_pool_pages_total", "100"),
        ("Innodb_buffer_pool_pages_data", "80"),
        ("Innodb_buffer_pool_pages_free", "20"),
        ("Innodb_buffer_pool_pages_dirty", "5"),
        ("Innodb_buffer_pool_read_requests", "90"),
        ("Innodb_buffer_pool_reads", "10"),
        ("Innodb_rows_read", "1"),
        ("Innodb_rows_inserted", "1"),
        ("Innodb_rows_updated", "1"),
        ("Innodb_rows_deleted", "1"),
        ("Innodb_row_lock_waits", "0"),
        ("Innodb_row_lock_time", "0"),
    ]
    conn = FakeConn(rows)
    with (
        patch.object(mon, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
        patch.object(mon, "get_mysql_connection_from_item", return_value=conn),
    ):
        out = json.loads(mon.get_innodb_stats.invoke({"config": {"configurable": {}}}))
    assert out["buffer_pool_hit_ratio"] == f"{calculate_percentage(90, 100)}%"
    assert out["buffer_pool_hit_ratio"] == "90.0%"
    assert out["buffer_pool_usage"] == f"{calculate_percentage(80, 100)}%"
    assert out["buffer_pool_usage"] == "80.0%"
    assert out["Innodb_row_lock_time_formatted"] == format_duration(0)
    assert conn.closed is True


def test_get_io_stats_formats_bytes():
    rows = [
        {
            "FILE_NAME": "/var/lib/mysql/ibdata1",
            "COUNT_READ": 10,
            "COUNT_WRITE": 4,
            "SUM_NUMBER_OF_BYTES_READ": 2048,
            "SUM_NUMBER_OF_BYTES_WRITE": 1024,
            "read_latency_ms": 12,
            "write_latency_ms": 8,
        }
    ]
    conn = FakeConn([])
    with (
        patch.object(mon, "build_mysql_normalized_from_runnable", return_value=NORMALIZED),
        patch.object(mon, "get_mysql_connection_from_item", return_value=conn),
        patch.object(mon, "execute_readonly_query", return_value=rows),
    ):
        out = json.loads(mon.get_io_stats.invoke({"config": {"configurable": {}}}))
    stat = out["io_stats"][0]
    assert out["io_file_count"] == 1
    assert stat["file_name"] == "/var/lib/mysql/ibdata1"
    assert stat["bytes_read"] == format_size(2048)
    assert stat["bytes_read"] == "2.00 KB"
    assert stat["bytes_write"] == format_size(1024)
    assert stat["bytes_write"] == "1.00 KB"
    assert stat["read_latency"] == format_duration(12)
    assert stat["read_latency"] == "12.00ms"
    assert stat["write_latency"] == format_duration(8)
    assert stat["write_latency"] == "8.00ms"
    assert conn.closed is True
