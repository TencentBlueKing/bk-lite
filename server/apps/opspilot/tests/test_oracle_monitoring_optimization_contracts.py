"""Oracle 监控与调优工具的公开行为契约。

仅在 Oracle 驱动连接边界使用协议一致的假连接；查询组装、只读事务、
结果计算和 JSON 序列化均执行真实生产代码。
"""

import json
from unittest.mock import patch

import oracledb
import pydantic.root_model  # noqa: F401
import pytest

from apps.opspilot.metis.llm.tools.oracle import monitoring, optimization


CONFIG = {
    "configurable": {
        "host": "127.0.0.1",
        "port": 1521,
        "service_name": "ORCL",
        "user": "system",
        "password": "secret",
    }
}


class OracleCursor:
    def __init__(self, responses):
        self.responses = responses
        self.description = []
        self.rows = []

    def execute(self, sql, params=None):
        if "SET TRANSACTION READ ONLY" in sql:
            return
        for marker, columns, rows in self.responses:
            if marker in sql:
                if isinstance(rows, Exception):
                    raise rows
                self.description = [(column,) for column in columns]
                self.rows = rows
                return
        self.description = []
        self.rows = []

    def fetchall(self):
        return list(self.rows)

    def close(self):
        return None


class OracleConnection:
    def __init__(self, responses):
        self.responses = responses
        self.closed = False

    def cursor(self):
        return OracleCursor(self.responses)

    def close(self):
        self.closed = True


pytestmark = pytest.mark.unit


def test_configuration_tuning_treats_null_memory_parameters_as_disabled():
    connection = OracleConnection(
        [
            (
                "FROM v$parameter",
                ("NAME", "VALUE", "DISPLAY_VALUE"),
                [
                    ("sga_target", None, None),
                    ("memory_target", None, None),
                    ("pga_aggregate_target", None, None),
                    ("shared_pool_size", None, None),
                ],
            )
        ]
    )

    with patch.object(
        optimization,
        "get_oracle_connection_from_item",
        return_value=connection,
    ):
        result = json.loads(
            optimization.check_configuration_tuning.invoke({"config": CONFIG})
        )

    assert "error" not in result
    assert {
        (item["item"], item["severity"])
        for item in result["recommendations"]
    } >= {
        ("SGA自动调优", "warning"),
        ("PGA自动调优", "warning"),
    }
    assert connection.closed is True


def test_table_metrics_treats_null_segment_size_as_zero():
    connection = OracleConnection(
        [
            (
                "FROM dba_segments",
                ("TABLE_SIZE",),
                [(None,)],
            ),
            (
                "FROM dba_tables",
                ("NUM_ROWS", "BLOCKS", "AVG_ROW_LEN", "LAST_ANALYZED"),
                [(7, 2, 64, "2026-07-30")],
            ),
            (
                "FROM dba_tab_statistics",
                ("STALE_STATS",),
                [("NO",)],
            ),
        ]
    )

    with patch.object(
        monitoring,
        "get_oracle_connection_from_item",
        return_value=connection,
    ):
        result = json.loads(
            monitoring.get_table_metrics.invoke(
                {
                    "table_name": "orders",
                    "db_schema": "ops",
                    "config": CONFIG,
                }
            )
        )

    assert result["owner"] == "OPS"
    assert result["table_name"] == "ORDERS"
    assert result["table_size_bytes"] == 0
    assert result["table_size"] == "0.00 B"
    assert connection.closed is True


def test_database_metrics_reports_cache_hit_ratio_from_oracle_counters():
    connection = OracleConnection(
        [
            (
                "FROM v$sysstat",
                ("NAME", "VALUE"),
                [
                    ("physical reads", 50),
                    ("physical writes", 20),
                    ("db block gets", 400),
                    ("consistent gets", 600),
                    ("user commits", 12),
                ],
            )
        ]
    )

    with patch.object(
        monitoring,
        "get_oracle_connection_from_item",
        return_value=connection,
    ):
        result = json.loads(
            monitoring.get_database_metrics.invoke({"config": CONFIG})
        )

    assert result["physical reads"] == 50
    assert result["user commits"] == 12
    assert result["buffer_cache_hit_ratio"] == "95.0%"
    assert connection.closed is True


def test_sga_pga_stats_returns_component_sizes_and_cache_ratio():
    connection = OracleConnection(
        [
            (
                "FROM v$sgastat",
                ("POOL", "NAME", "BYTES"),
                [("shared pool", "free memory", 2048)],
            ),
            (
                "SELECT NAME, VALUE FROM v$sga",
                ("NAME", "VALUE"),
                [("Fixed Size", 1024), ("Variable Size", 3072)],
            ),
            (
                "FROM v$pgastat",
                ("NAME", "VALUE"),
                [("total PGA allocated", 4096)],
            ),
            (
                "FROM v$sysstat",
                ("NAME", "VALUE"),
                [
                    ("db block gets", 300),
                    ("consistent gets", 700),
                    ("physical reads", 100),
                ],
            ),
        ]
    )

    with patch.object(
        monitoring,
        "get_oracle_connection_from_item",
        return_value=connection,
    ):
        result = json.loads(
            monitoring.get_sga_pga_stats.invoke({"config": CONFIG})
        )

    assert result["sga_components"]["Total"] == "4.00 KB"
    assert result["sga_detail_top20"] == [
        {
            "pool": "shared pool",
            "name": "free memory",
            "size": "2.00 KB",
        }
    ]
    assert result["pga_stats"]["total PGA allocated"] == 4096
    assert result["buffer_cache_hit_ratio"] == "90.0%"


def test_io_stats_calculates_average_latency_without_dividing_by_zero():
    connection = OracleConnection(
        [
            (
                "FROM v$filestat",
                ("FILE_NAME", "PHYRDS", "PHYWRTS", "READTIM", "WRITETIM"),
                [
                    ("/data/system01.dbf", 20, 10, 50, 25),
                    ("/data/empty.dbf", 0, 0, 5, 7),
                ],
            )
        ]
    )

    with patch.object(
        monitoring,
        "get_oracle_connection_from_item",
        return_value=connection,
    ):
        result = json.loads(monitoring.get_io_stats.invoke({"config": CONFIG}))

    assert result["datafile_count"] == 2
    assert result["io_stats"][0]["avg_read_time_cs"] == 2.5
    assert result["io_stats"][0]["avg_write_time_cs"] == 2.5
    assert result["io_stats"][1]["avg_read_time_cs"] == 0
    assert result["io_stats"][1]["avg_write_time_cs"] == 0


def test_redo_status_groups_member_files_and_archived_log_size():
    connection = OracleConnection(
        [
            (
                "FROM v$log l",
                (
                    "GROUP#",
                    "MEMBERS",
                    "BYTES",
                    "STATUS",
                    "SEQUENCE#",
                    "MEMBER",
                ),
                [
                    (1, 2, 1024, "CURRENT", 42, "/redo/a.log"),
                    (1, 2, 1024, "CURRENT", 42, "/redo/b.log"),
                ],
            ),
            (
                "FROM v$archived_log",
                (
                    "NAME",
                    "SEQUENCE#",
                    "FIRST_TIME",
                    "COMPLETION_TIME",
                    "BLOCKS",
                    "BLOCK_SIZE",
                ),
                [("/archive/42.arc", 42, "start", "done", 2, 512)],
            ),
            (
                "FROM v$database",
                ("LOG_MODE",),
                [("ARCHIVELOG",)],
            ),
        ]
    )

    with patch.object(
        monitoring,
        "get_oracle_connection_from_item",
        return_value=connection,
    ):
        result = json.loads(
            monitoring.check_redo_log_status.invoke({"config": CONFIG})
        )

    assert result["log_mode"] == "ARCHIVELOG"
    assert result["redo_log_groups"][0]["member_files"] == [
        "/redo/a.log",
        "/redo/b.log",
    ]
    assert result["recent_archived_logs"][0]["size"] == "1.00 KB"


def test_processlist_returns_active_sessions_with_query_filter_enabled():
    connection = OracleConnection(
        [
            (
                "FROM v$session",
                (
                    "SID",
                    "SERIAL#",
                    "USERNAME",
                    "PROGRAM",
                    "MACHINE",
                    "SQL_ID",
                    "EVENT",
                    "WAIT_CLASS",
                    "SECONDS_IN_WAIT",
                    "STATUS",
                    "TYPE",
                ),
                [
                    (
                        10,
                        20,
                        "APP",
                        "worker",
                        "node-1",
                        "abc",
                        "db file sequential read",
                        "User I/O",
                        3,
                        "ACTIVE",
                        "USER",
                    )
                ],
            )
        ]
    )

    with patch.object(
        monitoring,
        "get_oracle_connection_from_item",
        return_value=connection,
    ):
        result = json.loads(
            monitoring.get_processlist.invoke(
                {"active_only": True, "config": CONFIG}
            )
        )

    assert result["session_count"] == 1
    assert result["sessions"][0]["username"] == "APP"
    assert result["sessions"][0]["seconds_in_wait"] == 3


def test_tablespace_usage_reports_non_autoextensible_critical_space():
    connection = OracleConnection(
        [
            (
                "FROM",
                (
                    "TABLESPACE_NAME",
                    "CONTENTS",
                    "STATUS",
                    "TOTAL_BYTES",
                    "MAX_BYTES",
                    "FREE_BYTES",
                    "AUTOEXTENSIBLE",
                ),
                [
                    (
                        "USERS",
                        "PERMANENT",
                        "ONLINE",
                        1000,
                        1000,
                        40,
                        "NO",
                    )
                ],
            )
        ]
    )

    with patch.object(
        optimization,
        "get_oracle_connection_from_item",
        return_value=connection,
    ):
        result = json.loads(
            optimization.check_tablespace_usage.invoke({"config": CONFIG})
        )

    assert result["warning_count"] == 1
    assert result["tablespaces"][0]["usage_percent"] == 96.0
    assert result["warnings"][0]["severity"] == "critical"
    assert "未开启自动扩展" in result["warnings"][0]["message"]


def test_unused_indexes_falls_back_when_usage_view_is_unavailable():
    connection = OracleConnection(
        [
            (
                "dba_index_usage",
                (),
                oracledb.Error("ORA-00942"),
            ),
            (
                "v$sql_plan",
                ("OWNER", "INDEX_NAME", "TABLE_NAME", "INDEX_TYPE"),
                [("OPS", "IDX_ORDERS_STATUS", "ORDERS", "NORMAL")],
            ),
        ]
    )

    with patch.object(
        optimization,
        "get_oracle_connection_from_item",
        return_value=connection,
    ):
        result = json.loads(
            optimization.check_unused_indexes.invoke(
                {"db_schema": "ops", "config": CONFIG}
            )
        )

    assert result["schema_filter"] == "ops"
    assert result["total_count"] == 1
    assert result["unused_indexes"][0]["detection_method"] == (
        "v$sql_plan_absence"
    )


def test_table_fragmentation_reports_space_and_row_chaining_risks():
    connection = OracleConnection(
        [
            (
                "FROM dba_tables",
                (
                    "OWNER",
                    "TABLE_NAME",
                    "NUM_ROWS",
                    "BLOCKS",
                    "AVG_ROW_LEN",
                    "CHAIN_CNT",
                    "ACTUAL_BYTES",
                ),
                [("OPS", "ORDERS", 100, 10, 10, 20, 4000)],
            )
        ]
    )

    with patch.object(
        optimization,
        "get_oracle_connection_from_item",
        return_value=connection,
    ):
        result = json.loads(
            optimization.check_table_fragmentation.invoke(
                {"db_schema": "ops", "config": CONFIG}
            )
        )

    assert result["total_count"] == 1
    assert result["fragmented_tables"][0]["fragmentation_percent"] == 75.0
    assert result["warnings"][0]["severity"] == "critical"
    assert any("行迁移" in issue for issue in result["warnings"][0]["issues"])
