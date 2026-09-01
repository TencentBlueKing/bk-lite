"""Oracle 优化/监控工具：表空间、未用索引、碎片、调优建议与运行指标。

mock get_oracle_connection_from_item，按 SQL 关键字返回 canned 行；
断言使用率告警、命中率计算、权限不足回退与连接关闭。
"""
import json
import sys
from unittest.mock import patch

import oracledb

sys.modules["oracledb"] = oracledb

from apps.opspilot.metis.llm.tools.oracle import monitoring as mon  # noqa: E402
from apps.opspilot.metis.llm.tools.oracle import optimization as opt  # noqa: E402

OracleError = oracledb.Error
CONFIG = {"configurable": {"host": "127.0.0.1", "port": 1521, "service_name": "ORCL", "user": "sys", "password": "p"}}


def _desc(*names):
    return [(n,) for n in names]


class FakeCursor:
    def __init__(self, matchers):
        self._matchers = matchers
        self._desc = None
        self._rows = []
        self.closed = False

    @property
    def description(self):
        return self._desc

    def execute(self, sql, params=None):
        if "SET TRANSACTION" in sql:
            return
        for substr, payload in self._matchers:
            if substr in sql:
                if isinstance(payload, OracleError):
                    raise payload
                self._desc, self._rows = payload
                return
        self._desc, self._rows = [], []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self, matchers):
        self._matchers = matchers
        self.closed = False
        self.cursors = []

    def cursor(self):
        c = FakeCursor(self._matchers)
        self.cursors.append(c)
        return c

    def close(self):
        self.closed = True


def _patch(module, fake_conn):
    return patch.object(module, "get_oracle_connection_from_item", return_value=fake_conn)


class TestOracleOptimization:
    def test_tablespace_usage_warns_above_threshold(self):
        desc = _desc("TABLESPACE_NAME", "CONTENTS", "STATUS", "TOTAL_BYTES", "MAX_BYTES", "FREE_BYTES", "AUTOEXTENSIBLE")
        rows = [
            ("USERS", "PERMANENT", "ONLINE", 1000, 2000, 50, "NO"),  # 95% used
            ("TEMP", "TEMPORARY", "ONLINE", 1000, 0, 400, "YES"),  # 60% used
        ]
        fc = FakeConn([("dba_data_files", (desc, rows))])
        with _patch(opt, fc):
            out = json.loads(opt.check_tablespace_usage.invoke({"config": CONFIG}))
        assert out["total_count"] == 2
        users = next(ts for ts in out["tablespaces"] if ts["tablespace_name"] == "USERS")
        assert users["usage_percent"] == 95.0
        assert out["warning_count"] == 1
        assert out["warnings"][0]["severity"] == "warning"
        assert out["warnings"][0]["usage_percent"] == 95.0
        assert fc.closed is True

    def test_tablespace_usage_error_is_wrapped(self):
        fc = FakeConn([("dba_data_files", OracleError("ORA-01031"))])
        with _patch(opt, fc):
            out = json.loads(opt.check_tablespace_usage.invoke({"config": CONFIG}))
        assert "ORA-01031" in out["error"]
        assert fc.closed is True

    def test_unused_indexes_primary_path(self):
        desc = _desc("OWNER", "INDEX_NAME", "TABLE_NAME", "INDEX_TYPE", "TOTAL_ACCESS_COUNT", "LAST_USED")
        rows = [("APP", "IDX_UNUSED", "T1", "NORMAL", 0, None)]
        fc = FakeConn([("dba_index_usage", (desc, rows))])
        with _patch(opt, fc):
            out = json.loads(opt.check_unused_indexes.invoke({"config": CONFIG}))
        assert out["total_count"] == 1
        assert out["unused_indexes"][0]["detection_method"] == "dba_index_usage"
        assert "DROP INDEX" in out["recommendation"]

    def test_unused_indexes_falls_back_when_usage_view_missing(self):
        fallback_desc = _desc("OWNER", "INDEX_NAME", "TABLE_NAME", "INDEX_TYPE")
        fc = FakeConn(
            [
                ("dba_index_usage", OracleError("ORA-00942")),
                ("v$sql_plan", (fallback_desc, [("APP", "IDX2", "T2", "BITMAP")])),
            ]
        )
        with _patch(opt, fc):
            out = json.loads(opt.check_unused_indexes.invoke({"db_schema": "app", "config": CONFIG}))
        assert out["unused_indexes"][0]["detection_method"] == "v$sql_plan_absence"
        assert out["schema_filter"] == "app"

    def test_table_fragmentation_skips_healthy_tables(self):
        desc = _desc("OWNER", "TABLE_NAME", "NUM_ROWS", "BLOCKS", "AVG_ROW_LEN", "CHAIN_CNT", "ACTUAL_BYTES")
        # healthy: fragmentation <= 30 and chain_cnt=0
        healthy = ("APP", "OK_TAB", 100, 10, 80, 0, 8000)
        # fragmented: actual much larger than estimated
        bad = ("APP", "FRAG_TAB", 100, 50, 10, 5, 100000)
        fc = FakeConn([("dba_tables", (desc, [healthy, bad]))])
        with _patch(opt, fc):
            out = json.loads(opt.check_table_fragmentation.invoke({"config": CONFIG}))
        names = [t["table_name"] for t in out["fragmented_tables"]]
        assert "FRAG_TAB" in names
        assert "OK_TAB" not in names

    def test_configuration_tuning_amm_and_low_hit_ratio(self):
        param_desc = _desc("NAME", "VALUE", "DISPLAY_VALUE")
        param_rows = [
            ("sga_target", "0", "0"),
            ("memory_target", "1073741824", "1G"),
            ("pga_aggregate_target", "0", "0"),
            ("shared_pool_size", "1000", "1000"),
            ("processes", "100", "100"),
            ("sessions", "200", "200"),
        ]
        hit_desc = _desc("HIT_RATIO")
        sp_desc = _desc("BYTES")
        redo_desc = _desc("GROUP#", "BYTES", "STATUS")
        proc_desc = _desc("CNT")
        fc = FakeConn(
            [
                ("FROM v$parameter", (param_desc, param_rows)),
                ("FROM v$sysstat", (hit_desc, [(0.80,)])),  # 80% -> critical
                ("v$sgastat", (sp_desc, [(20,)])),  # 2% free of 1000
                ("FROM v$log", (redo_desc, [(1, 10 * 1024 * 1024, "CURRENT")])),
                ("FROM v$process", (proc_desc, [(95,)])),
            ]
        )
        with _patch(opt, fc):
            out = json.loads(opt.check_configuration_tuning.invoke({"config": CONFIG}))
        items = {r["item"]: r for r in out["recommendations"]}
        assert "自动内存管理(AMM)" in items
        assert items["缓冲区缓存命中率"]["severity"] == "critical"
        assert out["critical_count"] >= 1
        assert fc.closed is True


class TestOracleMonitoring:
    def test_database_metrics_computes_hit_ratio(self):
        desc = _desc("NAME", "VALUE")
        rows = [
            ("physical reads", 10),
            ("physical writes", 2),
            ("redo writes", 1),
            ("user commits", 5),
            ("user rollbacks", 1),
            ("parse count (total)", 8),
            ("execute count", 20),
            ("db block gets", 40),
            ("consistent gets", 60),
        ]
        fc = FakeConn([("v$sysstat", (desc, rows))])
        with _patch(mon, fc):
            out = json.loads(mon.get_database_metrics.invoke({"config": CONFIG}))
        # (100-10)/100 = 90%
        assert out["buffer_cache_hit_ratio"] == "90.0%"
        assert out["user commits"] == 5
        assert fc.closed is True

    def test_table_metrics_uses_schema_and_wraps_error(self):
        size_desc = _desc("TABLE_SIZE")
        info_desc = _desc("NUM_ROWS", "BLOCKS", "AVG_ROW_LEN", "LAST_ANALYZED")
        stale_desc = _desc("STALE_STATS")
        fc = FakeConn(
            [
                ("dba_segments", (size_desc, [(4096,)])),
                ("dba_tab_statistics", (stale_desc, [("YES",)])),
                ("FROM dba_tables", (info_desc, [(10, 2, 80, None)])),
            ]
        )
        with _patch(mon, fc):
            out = json.loads(mon.get_table_metrics.invoke({"table_name": "orders", "db_schema": "sales", "config": CONFIG}))
        assert out["owner"] == "SALES"
        assert out["table_name"] == "ORDERS"
        assert out["num_rows"] == 10
        assert out["table_size_bytes"] == 4096
        assert out["stale_stats"] == "YES"

        fc_err = FakeConn([("dba_segments", OracleError("ORA-00942"))])
        with _patch(mon, fc_err):
            err = json.loads(mon.get_table_metrics.invoke({"table_name": "x", "config": CONFIG}))
        assert "ORA-00942" in err["error"]

    def test_sga_pga_stats_aggregates_components(self):
        sga_desc = _desc("NAME", "VALUE")
        sgastat_desc = _desc("POOL", "NAME", "BYTES")
        pga_desc = _desc("NAME", "VALUE")
        hit_desc = _desc("NAME", "VALUE")
        fc = FakeConn(
            [
                ("FROM v$sgastat", (sgastat_desc, [("shared pool", "free memory", 50)])),
                ("FROM v$pgastat", (pga_desc, [("aggregate PGA target parameter", 200)])),
                ("FROM v$sysstat", (hit_desc, [("physical reads", 1), ("db block gets", 10), ("consistent gets", 10)])),
                ("FROM v$sga", (sga_desc, [("Fixed Size", 100), ("Variable Size", 900)])),
            ]
        )
        with _patch(mon, fc):
            out = json.loads(mon.get_sga_pga_stats.invoke({"config": CONFIG}))
        assert out["sga_components"]["Total"]
        assert out["pga_stats"]["aggregate PGA target parameter"] == 200
        assert out["buffer_cache_hit_ratio"] == "95.0%"
        assert fc.closed is True

    def test_io_stats_computes_averages(self):
        desc = _desc("FILE_NAME", "PHYRDS", "PHYWRTS", "READTIM", "WRITETIM")
        rows = [("/u01/oradata/sys.dbf", 10, 5, 20, 10)]
        fc = FakeConn([("v$filestat", (desc, rows))])
        with _patch(mon, fc):
            out = json.loads(mon.get_io_stats.invoke({"config": CONFIG}))
        assert out["datafile_count"] == 1
        assert out["io_stats"][0]["avg_read_time_cs"] == 2.0
        assert out["io_stats"][0]["avg_write_time_cs"] == 2.0

    def test_redo_log_status_groups_members(self):
        redo_desc = _desc("GROUP#", "MEMBERS", "BYTES", "STATUS", "SEQUENCE#", "MEMBER")
        redo_rows = [(1, 2, 104857600, "CURRENT", 10, "/u01/redo01.log"), (1, 2, 104857600, "CURRENT", 10, "/u02/redo01.log")]
        mode_desc = _desc("LOG_MODE", "FORCE_LOGGING")
        arch_desc = _desc("NAME", "SEQUENCE#", "STATUS")
        fc = FakeConn(
            [
                ("v$logfile", (redo_desc, redo_rows)),
                ("v$database", (mode_desc, [("ARCHIVELOG", "YES")])),
                ("v$archived_log", (arch_desc, [])),
            ]
        )
        with _patch(mon, fc):
            out = json.loads(mon.check_redo_log_status.invoke({"config": CONFIG}))
        assert out["log_mode"] == "ARCHIVELOG"
        assert len(out["redo_log_groups"]) == 1
        assert out["redo_log_groups"][0]["member_files"] == ["/u01/redo01.log", "/u02/redo01.log"]

    def test_processlist_filters_active_user_sessions(self):
        desc = _desc("SID", "SERIAL#", "USERNAME", "PROGRAM", "MACHINE", "SQL_ID", "EVENT", "WAIT_CLASS", "SECONDS_IN_WAIT", "STATUS", "TYPE")
        rows = [(1, 2, "APP", "sqlplus", "host", "abc", "db file sequential read", "User I/O", 3, "ACTIVE", "USER")]
        fc = FakeConn([("v$session", (desc, rows))])
        with _patch(mon, fc):
            out = json.loads(mon.get_processlist.invoke({"active_only": True, "config": CONFIG}))
        assert out["session_count"] == 1
        assert out["sessions"][0]["sid"] == 1
        assert out["sessions"][0]["username"] == "APP"
