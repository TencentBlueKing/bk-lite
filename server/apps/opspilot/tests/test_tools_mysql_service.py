"""MySQL @tool 工具集单元测试 (mysql/monitoring|analysis|optimization)。

mock 边界为 get_mysql_connection_from_item(driver 连接获取),返回带 FakeCursor 的
假连接;FakeCursor 按 SQL 关键字返回真实形态行数据,支持 tuple/dict 两种游标模式。
断言工具输出的结构化 JSON、派生指标(QPS/命中率/碎片率)、performance_schema 异常
翻译、Error 透出与连接关闭契约。不连真实 MySQL。
"""

import json
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest
from mysql.connector import Error

from apps.opspilot.metis.llm.tools.mysql import analysis as ana
from apps.opspilot.metis.llm.tools.mysql import monitoring as mon
from apps.opspilot.metis.llm.tools.mysql import optimization as opt

# 单实例 legacy 配置 -> normalize_credentials 产生单 item, single 模式直接 unwrap
CONFIG = {"configurable": {"host": "127.0.0.1", "port": 3306, "user": "root", "database": "appdb"}}


class FakeCursor:
    """按 SQL 关键字分派 canned 结果的假游标。

    matchers: list[(预测函数, (description, rows))]。
    dictionary=True 时 fetchall/fetchone 返回 dict 行,否则返回 tuple 行。
    """

    def __init__(self, matchers, dictionary=False):
        self._matchers = matchers
        self._dictionary = dictionary
        self._desc = None
        self._rows = []
        self.closed = False
        self.executed = []

    @property
    def description(self):
        return self._desc

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        for pred, (desc, rows) in self._matchers:
            if pred(sql):
                self._desc = desc
                self._rows = rows
                return
        # 未匹配: 空结果集
        self._desc = []
        self._rows = []

    def _as_rows(self):
        if self._dictionary:
            cols = [c[0] for c in (self._desc or [])]
            return [dict(zip(cols, r)) if not isinstance(r, dict) else r for r in self._rows]
        return list(self._rows)

    def fetchall(self):
        return self._as_rows()

    def fetchone(self):
        rows = self._as_rows()
        return rows[0] if rows else None

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self, matchers):
        self._matchers = matchers
        self.closed = False
        self.cursors = []

    def cursor(self, dictionary=False):
        c = FakeCursor(self._matchers, dictionary=dictionary)
        self.cursors.append(c)
        return c

    def close(self):
        self.closed = True


def _patch_conn(module, conn):
    return patch.object(module, "get_mysql_connection_from_item", return_value=conn)


def _desc(*names):
    return [(n,) for n in names]


# ---------------- monitoring.get_database_metrics ----------------
class TestDatabaseMetrics:
    def _conn(self, status):
        rows = list(status.items())
        return FakeConn([(lambda s: "GLOBAL STATUS" in s, (_desc("Variable_name", "Value"), rows))])

    def test_qps_tps_and_formatting(self):
        status = {
            "Questions": "2000",
            "Com_insert": "10",
            "Com_update": "20",
            "Com_delete": "10",
            "Threads_connected": "5",
            "Threads_running": "2",
            "Uptime": "100",
            "Bytes_received": "2048",
            "Bytes_sent": "1048576",
            "Slow_queries": "3",
        }
        conn = self._conn(status)
        with _patch_conn(mon, conn):
            out = json.loads(mon.get_database_metrics.invoke({"config": CONFIG}))
        assert out["QPS"] == 20.0  # 2000/100
        assert out["TPS"] == 0.4  # (10+20+10)/100
        assert out["Bytes_received_formatted"] == "2.00 KB"
        assert out["Bytes_sent_formatted"] == "1.00 MB"
        assert out["Threads_connected"] == 5
        assert out["Slow_queries"] == 3
        assert conn.closed is True

    def test_non_numeric_status_passthrough(self):
        # 非数字状态值原样保留, isdigit() False 分支
        status = {k: "0" for k in ["Questions", "Com_insert", "Com_update", "Com_delete",
                                   "Threads_connected", "Threads_running", "Uptime",
                                   "Bytes_received", "Bytes_sent", "Slow_queries"]}
        status["Threads_connected"] = "N/A"
        conn = self._conn(status)
        with _patch_conn(mon, conn):
            out = json.loads(mon.get_database_metrics.invoke({"config": CONFIG}))
        assert out["Threads_connected"] == "N/A"

    def test_error_translated(self):
        conn = MagicMock()
        conn.cursor.side_effect = Error("connection refused")
        with _patch_conn(mon, conn):
            out = json.loads(mon.get_database_metrics.invoke({"config": CONFIG}))
        assert out["error"] == "connection refused"
        conn.close.assert_called_once()


# ---------------- monitoring.get_innodb_stats ----------------
class TestInnodbStats:
    def test_hit_ratio_and_usage(self):
        status = {
            "Innodb_buffer_pool_pages_total": "1000",
            "Innodb_buffer_pool_pages_data": "800",
            "Innodb_buffer_pool_pages_free": "200",
            "Innodb_buffer_pool_pages_dirty": "10",
            "Innodb_buffer_pool_read_requests": "990",
            "Innodb_buffer_pool_reads": "10",
            "Innodb_rows_read": "5",
            "Innodb_rows_inserted": "1",
            "Innodb_rows_updated": "1",
            "Innodb_rows_deleted": "0",
            "Innodb_row_lock_waits": "0",
            "Innodb_row_lock_time": "1500",
        }
        conn = FakeConn([(lambda s: "GLOBAL STATUS" in s, (_desc("k", "v"), list(status.items())))])
        with _patch_conn(mon, conn):
            out = json.loads(mon.get_innodb_stats.invoke({"config": CONFIG}))
        assert out["buffer_pool_hit_ratio"] == "99.0%"  # 990/1000
        assert out["buffer_pool_usage"] == "80.0%"  # 800/1000
        assert out["Innodb_row_lock_time_formatted"] == "1.50s"

    def test_zero_requests_defaults_100(self):
        status = {k: "0" for k in [
            "Innodb_buffer_pool_pages_total", "Innodb_buffer_pool_pages_data",
            "Innodb_buffer_pool_pages_free", "Innodb_buffer_pool_pages_dirty",
            "Innodb_buffer_pool_read_requests", "Innodb_buffer_pool_reads",
            "Innodb_rows_read", "Innodb_rows_inserted", "Innodb_rows_updated",
            "Innodb_rows_deleted", "Innodb_row_lock_waits", "Innodb_row_lock_time"]}
        conn = FakeConn([(lambda s: "GLOBAL STATUS" in s, (_desc("k", "v"), list(status.items())))])
        with _patch_conn(mon, conn):
            out = json.loads(mon.get_innodb_stats.invoke({"config": CONFIG}))
        assert out["buffer_pool_hit_ratio"] == "100.0%"
        assert out["buffer_pool_usage"] == "0.0%"


# ---------------- monitoring.get_table_metrics ----------------
class TestTableMetrics:
    def test_fragmentation_and_sizes(self):
        rows = [(
            "orders", "InnoDB", 1000,
            1048576, 524288, 104857,  # data, index, free
            5000, "2024-01-01", "2024-06-01",
        )]
        desc = _desc("TABLE_NAME", "ENGINE", "TABLE_ROWS", "DATA_LENGTH",
                     "INDEX_LENGTH", "DATA_FREE", "AUTO_INCREMENT", "CREATE_TIME", "UPDATE_TIME")
        conn = FakeConn([(lambda s: "information_schema.TABLES" in s, (desc, rows))])
        with _patch_conn(mon, conn):
            out = json.loads(mon.get_table_metrics.invoke({"database": "shop", "config": CONFIG}))
        assert out["database"] == "shop"
        assert out["table_count"] == 1
        t = out["tables"][0]
        assert t["table_name"] == "orders"
        assert t["total_size"] == "1.50 MB"  # 1MB + 512KB
        # frag = 104857 / 1572864 *100 ≈ 6.67%
        assert t["fragmentation_ratio"] == "6.67%"

    def test_explicit_database_used_over_item_config(self):
        # 显式传 database 参数优先于 item 配置
        conn = FakeConn([(lambda s: "information_schema.TABLES" in s, (_desc("TABLE_NAME"), []))])
        with _patch_conn(mon, conn):
            out = json.loads(mon.get_table_metrics.invoke({"database": "explicit_db", "config": CONFIG}))
        assert out["database"] == "explicit_db"
        assert out["table_count"] == 0
        # WHERE TABLE_SCHEMA = %s 参数应转发 explicit_db
        assert conn.cursors[0].executed[-1][1] == ("explicit_db",)


# ---------------- monitoring.check_replication_status ----------------
class TestReplicationStatus:
    def test_not_configured(self):
        conn = FakeConn([(lambda s: "REPLICA STATUS" in s, (_desc("x"), []))])
        with _patch_conn(mon, conn):
            out = json.loads(mon.check_replication_status.invoke({"config": CONFIG}))
        assert out["replication_configured"] is False
        assert out["message"] == "未配置复制"

    def test_replica_naming_normalized(self):
        row = {
            "Source_Host": "10.0.0.1", "Source_Port": 3306,
            "Replica_IO_Running": "Yes", "Replica_SQL_Running": "Yes",
            "Seconds_Behind_Source": 0, "Relay_Log_Space": 4096,
        }
        conn = FakeConn([(lambda s: "REPLICA STATUS" in s, (_desc("dummy"), [row]))])
        with _patch_conn(mon, conn):
            out = json.loads(mon.check_replication_status.invoke({"config": CONFIG}))
        assert out["replication_configured"] is True
        assert out["source_host"] == "10.0.0.1"
        assert out["replica_io_running"] == "Yes"
        assert out["relay_log_space"] == "4.00 KB"

    def test_fallback_to_slave_status(self):
        # SHOW REPLICA STATUS 抛 Error -> fallback SHOW SLAVE STATUS
        def matcher(sql):
            return "SLAVE STATUS" in sql

        slave_row = {"Master_Host": "db-old", "Slave_IO_Running": "Yes"}

        class RepConn(FakeConn):
            def cursor(self, dictionary=False):
                c = FakeCursorReplica(dictionary=dictionary, slave_row=slave_row)
                self.cursors.append(c)
                return c

        conn = RepConn([])
        with _patch_conn(mon, conn):
            out = json.loads(mon.check_replication_status.invoke({"config": CONFIG}))
        assert out["replication_configured"] is True
        assert out["source_host"] == "db-old"


class FakeCursorReplica:
    """SHOW REPLICA STATUS 抛 Error, SHOW SLAVE STATUS 返回行。"""

    def __init__(self, dictionary=False, slave_row=None):
        self._row = None
        self._slave_row = slave_row

    def execute(self, sql, params=None):
        if "REPLICA STATUS" in sql:
            raise Error("Unknown command")
        if "SLAVE STATUS" in sql:
            self._row = self._slave_row

    def fetchone(self):
        return self._row

    def close(self):
        pass


# ---------------- monitoring.get_processlist ----------------
class TestProcesslist:
    def test_filters_idle_sleep(self):
        rows = [
            {"Id": 1, "User": "app", "Host": "h", "db": "d", "Command": "Sleep", "Time": 5, "State": "", "Info": None},
            {"Id": 2, "User": "app", "Host": "h", "db": "d", "Command": "Query", "Time": 1, "State": "executing", "Info": "SELECT 1"},
        ]
        conn = FakeConn([(lambda s: "PROCESSLIST" in s, (_desc("x"), rows))])
        with _patch_conn(mon, conn):
            out = json.loads(mon.get_processlist.invoke({"config": CONFIG}))
        assert out["active_process_count"] == 1
        assert out["processes"][0]["id"] == 2
        assert out["processes"][0]["info"] == "SELECT 1"


# ---------------- monitoring.check_binary_log_status ----------------
class TestBinaryLog:
    def test_binlog_on_lists_files(self):
        class BinlogCursor:
            def __init__(self, dictionary=False):
                self._rows = []
                self._one = None

            def execute(self, sql, params=None):
                if "log_bin" in sql and "binlog" not in sql.replace("log_bin", ""):
                    self._one = ("log_bin", "ON")
                elif "binlog_format" in sql:
                    self._one = ("binlog_format", "ROW")
                elif "expire_logs_days" in sql:
                    self._one = ("expire_logs_days", "7")
                elif "binlog_expire_logs_seconds" in sql:
                    self._one = ("binlog_expire_logs_seconds", "604800")
                elif "BINARY LOGS" in sql:
                    self._rows = [("binlog.000001", 1024), ("binlog.000002", 2048)]

            def fetchone(self):
                return self._one

            def fetchall(self):
                return self._rows

            def close(self):
                pass

        class C(FakeConn):
            def cursor(self, dictionary=False):
                return BinlogCursor(dictionary)

        conn = C([])
        with _patch_conn(mon, conn):
            out = json.loads(mon.check_binary_log_status.invoke({"config": CONFIG}))
        assert out["log_bin"] == "ON"
        assert out["binlog_format"] == "ROW"
        assert out["binlog_file_count"] == 2
        assert out["total_binlog_size"] == "3.00 KB"


# ---------------- analysis.analyze_buffer_pool_usage ----------------
class TestBufferPoolAnalysis:
    def _conn(self, status):
        return FakeConn([(lambda s: "GLOBAL STATUS" in s,
                          (_desc("Variable_name", "Value"), list(status.items())))])

    def test_good_hit_ratio(self):
        status = {
            "Innodb_buffer_pool_pages_total": "1000",
            "Innodb_buffer_pool_pages_data": "700",
            "Innodb_buffer_pool_pages_free": "300",
            "Innodb_buffer_pool_pages_dirty": "50",
            "Innodb_buffer_pool_pages_flushed": "5",
            "Innodb_buffer_pool_read_requests": "10000",
            "Innodb_buffer_pool_reads": "100",
        }
        with _patch_conn(ana, self._conn(status)):
            out = json.loads(ana.analyze_buffer_pool_usage.invoke({"config": CONFIG}))
        assert out["hit_ratio_percent"] == 99.0  # (10000-100)/10000
        assert out["dirty_ratio_percent"] == 5.0
        assert out["utilization_percent"] == 70.0
        assert out["recommendation"] == "缓冲池命中率良好"

    def test_low_hit_ratio_recommends_increase(self):
        status = {
            "Innodb_buffer_pool_pages_total": "100",
            "Innodb_buffer_pool_pages_data": "50",
            "Innodb_buffer_pool_pages_free": "50",
            "Innodb_buffer_pool_pages_dirty": "0",
            "Innodb_buffer_pool_pages_flushed": "0",
            "Innodb_buffer_pool_read_requests": "100",
            "Innodb_buffer_pool_reads": "50",  # 命中率 50%
        }
        with _patch_conn(ana, self._conn(status)):
            out = json.loads(ana.analyze_buffer_pool_usage.invoke({"config": CONFIG}))
        assert out["hit_ratio_percent"] == 50.0
        assert "innodb_buffer_pool_size" in out["recommendation"]


# ---------------- analysis.analyze_query_patterns ----------------
class TestQueryPatterns:
    def test_classifies_scans_and_joins(self):
        desc = _desc("DIGEST_TEXT", "SCHEMA_NAME", "COUNT_STAR", "SUM_TIMER_WAIT",
                     "AVG_TIMER_WAIT", "SUM_ROWS_EXAMINED", "SUM_ROWS_SENT",
                     "SUM_SELECT_FULL_JOIN", "SUM_SELECT_SCAN", "SUM_SORT_MERGE_PASSES")
        rows = [
            ("SELECT a", "app", 100, 9, 9, 50, 50, 0, 2, 0),  # full scan
            ("SELECT b JOIN", "app", 80, 9, 9, 99, 1, 3, 0, 1),  # full join
            ("SELECT c", "app", 10, 1, 1, 1, 1, 0, 0, 0),  # clean
        ]
        conn = FakeConn([(lambda s: "events_statements_summary" in s, (desc, rows))])
        with _patch_conn(ana, conn):
            out = json.loads(ana.analyze_query_patterns.invoke({"config": CONFIG}))
        assert out["summary"]["total_patterns"] == 3
        assert out["summary"]["full_table_scan_count"] == 1
        assert out["summary"]["full_join_count"] == 1
        assert out["full_table_scans"][0]["digest_text"] == "SELECT a"

    def test_performance_schema_unavailable_translated(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.execute.side_effect = Error("Table 'performance_schema.x' doesn't exist")
        conn.cursor.return_value = cur
        with _patch_conn(ana, conn):
            out = json.loads(ana.analyze_query_patterns.invoke({"config": CONFIG}))
        assert "performance_schema 不可用" in out["error"]


# ---------------- optimization.recommend_index_optimization ----------------
class TestIndexOptimization:
    def test_detects_duplicate_and_redundant(self):
        desc = _desc("TABLE_SCHEMA", "TABLE_NAME", "INDEX_NAME", "SEQ_IN_INDEX", "COLUMN_NAME")
        rows = [
            # idx_a (col1) is prefix of idx_b (col1,col2) -> redundant
            ("app", "t", "idx_a", 1, "col1"),
            ("app", "t", "idx_b", 1, "col1"),
            ("app", "t", "idx_b", 2, "col2"),
            # idx_c and idx_d both (col3) -> duplicate
            ("app", "t", "idx_c", 1, "col3"),
            ("app", "t", "idx_d", 1, "col3"),
        ]
        conn = FakeConn([(lambda s: "information_schema.STATISTICS" in s, (desc, rows))])
        with _patch_conn(opt, conn):
            out = json.loads(opt.recommend_index_optimization.invoke({"database": "app", "config": CONFIG}))
        types = {r["type"] for r in out["recommendations"]}
        assert "duplicate" in types
        assert "redundant" in types
        assert out["total_count"] >= 2

    def test_no_redundancy(self):
        desc = _desc("TABLE_SCHEMA", "TABLE_NAME", "INDEX_NAME", "SEQ_IN_INDEX", "COLUMN_NAME")
        rows = [("app", "t", "idx_a", 1, "col1"), ("app", "t", "idx_b", 1, "col2")]
        conn = FakeConn([(lambda s: "information_schema.STATISTICS" in s, (desc, rows))])
        with _patch_conn(opt, conn):
            out = json.loads(opt.recommend_index_optimization.invoke({"config": CONFIG}))
        assert out["total_count"] == 0
        assert out["summary"] == "未发现冗余或重复索引"


# ---------------- optimization.check_unused_indexes ----------------
class TestUnusedIndexes:
    def test_found_recommends_drop(self):
        desc = _desc("OBJECT_SCHEMA", "TABLE_NAME", "INDEX_NAME")
        rows = [("app", "t", "idx_dead")]
        conn = FakeConn([(lambda s: "table_io_waits_summary_by_index_usage" in s, (desc, rows))])
        with _patch_conn(opt, conn):
            out = json.loads(opt.check_unused_indexes.invoke({"database": "app", "config": CONFIG}))
        assert out["total_count"] == 1
        assert "删除未使用的索引" in out["recommendation"]

    def test_perf_schema_error_translated(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.execute.side_effect = Error("performance_schema not enabled")
        conn.cursor.return_value = cur
        with _patch_conn(opt, conn):
            out = json.loads(opt.check_unused_indexes.invoke({"config": CONFIG}))
        assert "performance_schema 不可用" in out["error"]


# ---------------- optimization.check_table_fragmentation ----------------
class TestTableFragmentation:
    def test_high_frag_flagged(self):
        desc = _desc("TABLE_NAME", "ENGINE", "TABLE_ROWS", "DATA_LENGTH",
                     "INDEX_LENGTH", "DATA_FREE", "frag_percent")
        rows = [
            ("hot", "InnoDB", 100, 1000, 0, 500, 30.5),  # >20 高碎片
            ("cold", "InnoDB", 100, 1000, 0, 50, 5.0),
        ]
        conn = FakeConn([(lambda s: "information_schema.TABLES" in s, (desc, rows))])
        with _patch_conn(opt, conn):
            out = json.loads(opt.check_table_fragmentation.invoke({"database": "app", "config": CONFIG}))
        assert out["total_count"] == 2
        assert out["high_fragmentation_tables"] == ["hot"]
        assert "OPTIMIZE TABLE" in out["recommendation"]


# ---------------- optimization.check_configuration_tuning ----------------
class TestConfigTuning:
    def test_high_connection_usage_advice(self):
        variables = {
            "innodb_buffer_pool_size": str(8 * 1024 ** 3),
            "max_connections": "100",
            "innodb_log_file_size": str(256 * 1024 ** 2),
            "innodb_flush_log_at_trx_commit": "1",
            "tmp_table_size": str(16 * 1024 ** 2),
            "max_heap_table_size": str(16 * 1024 ** 2),
        }
        status = {
            "Max_used_connections": "90",  # 90% > 85
            "Created_tmp_disk_tables": "40",
            "Created_tmp_tables": "100",  # 40% > 25
        }

        def matcher(sql):
            return "VARIABLES" in sql

        conn = FakeConn([
            (lambda s: "VARIABLES" in s, (_desc("Variable_name", "Value"), list(variables.items()))),
            (lambda s: "STATUS" in s, (_desc("Variable_name", "Value"), list(status.items()))),
        ])
        with _patch_conn(opt, conn):
            out = json.loads(opt.check_configuration_tuning.invoke({"config": CONFIG}))
        recs = {r["variable"]: r for r in out["recommendations"]}
        assert recs["max_connections"]["usage_percent"] == 90.0
        assert "建议适当增大" in recs["max_connections"]["advice"]
        assert recs["innodb_buffer_pool_size"]["current_value"] == "8.00 GB"
        tmp = recs["tmp_table_size / max_heap_table_size"]
        assert tmp["disk_tmp_table_percent"] == 40.0
        assert "建议增大" in tmp["advice"]
