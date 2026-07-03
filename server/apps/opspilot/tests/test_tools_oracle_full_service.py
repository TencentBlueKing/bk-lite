"""Oracle @tool 工具集单元测试 (oracle/diagnostics|resources|connection)。

mock 边界为 get_oracle_connection_from_item(driver 连接获取),返回带 FakeCursor 的假连接;
FakeCursor 忽略 'SET TRANSACTION READ ONLY',按 SQL 关键字返回真实形态(description+tuple
行,Oracle 风格大写列名)。execute_readonly_query 保持真实 zip→dict 逻辑。
断言工具产出的结构化 JSON、健康评分、会话使用率、表空间使用率、缓存命中率、Data Guard
角色分支、权限不足 fallback、oracledb.Error 透出与连接关闭契约。不连真实 Oracle。

防御性重绑: 存量 test_kubernetes_data_collection_tools.py 用 sys.modules.setdefault
注入了一个假的 oracledb stub,这里先 import 真实 oracledb 再强制重绑,避免被污染。
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest

import oracledb  # noqa: E402

sys.modules["oracledb"] = oracledb  # 防御性重绑, 抵御其他测试文件的 sys.modules 污染

from apps.opspilot.metis.llm.tools.oracle import connection as conn  # noqa: E402
from apps.opspilot.metis.llm.tools.oracle import diagnostics as diag  # noqa: E402
from apps.opspilot.metis.llm.tools.oracle import resources as res  # noqa: E402

OracleError = oracledb.Error

CONFIG = {"configurable": {"host": "127.0.0.1", "port": 1521, "service_name": "ORCL", "user": "sys", "password": "p"}}


def _desc(*names):
    return [(n,) for n in names]


class FakeCursor:
    """忽略 SET TRANSACTION, 按 SQL 子串分派 canned (description, rows) 的假游标。

    matchers: list[(substr, (description, rows))]; rows 为 tuple 列表。
    某 matcher 的第二项可为 OracleError 实例 -> execute 时抛出(模拟无权限/视图缺失)。
    """

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


# ============================ diagnostics ============================
class TestOracleDiagnostics:
    def test_slow_queries_derives_avg_and_formats(self):
        desc = _desc("SQL_ID", "SQL_TEXT", "EXECUTIONS", "ELAPSED_TIME", "CPU_TIME", "BUFFER_GETS", "DISK_READS")
        rows = [("abc", "SELECT 1", 4, 8_000_000, 4_000_000, 100, 5)]  # elapsed 8e6 us
        fc = FakeConn([("v$sql", (desc, rows))])
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_slow_queries.invoke({"config": CONFIG}))
        q = out["slow_queries"][0]
        # elapsed_time_formatted: 8e6/1000 = 8000ms -> 8.00s
        assert q["elapsed_time_formatted"] == "8.00s"
        assert q["avg_elapsed_us"] == 2_000_000.0  # 8e6 / 4
        assert fc.closed is True

    def test_slow_queries_error(self):
        fc = MagicMock()
        fc.cursor.side_effect = OracleError("ORA-00942")
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_slow_queries.invoke({"config": CONFIG}))
        assert "ORA-00942" in out["error"]
        fc.close.assert_called_once()

    def test_lock_conflicts_with_dba_waiters(self):
        lock_desc = _desc("BLOCKER_SID", "WAITER_SID", "WAIT_SECONDS")
        lock_rows = [(10, 20, 30)]
        dba_desc = _desc("WAITING_SESSION", "HOLDING_SESSION", "LOCK_TYPE", "MODE_HELD", "MODE_REQUESTED")
        dba_rows = [(20, 10, "TX", "Exclusive", "Share")]
        fc = FakeConn([("FROM v$lock w", (lock_desc, lock_rows)), ("dba_waiters", (dba_desc, dba_rows))])
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_lock_conflicts.invoke({"config": CONFIG}))
        assert out["has_conflicts"] is True
        assert out["total_lock_conflicts"] == 1
        assert out["dba_waiters"][0]["WAITING_SESSION"] == 20

    def test_lock_conflicts_dba_waiters_permission_denied(self):
        lock_desc = _desc("BLOCKER_SID", "WAITER_SID")
        fc = FakeConn([("FROM v$lock w", (lock_desc, [(1, 2)])), ("dba_waiters", OracleError("ORA-00942"))])
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_lock_conflicts.invoke({"config": CONFIG}))
        assert out["has_conflicts"] is True
        assert out["dba_waiters"] == []

    def test_connection_issues_session_usage_and_warning(self):
        param_desc = _desc("NAME", "VALUE")
        param_rows = [("processes", "150"), ("sessions", "100")]
        sess_desc = _desc("STATUS", "CNT")
        sess_rows = [("ACTIVE", 60), ("INACTIVE", 35)]  # total 95 / 100 = 95%
        user_desc = _desc("USERNAME", "CNT")
        user_rows = [("APP", 50), ("RPT", 45)]
        fc = FakeConn([
            ("v$parameter", (param_desc, param_rows)),
            ("GROUP BY status", (sess_desc, sess_rows)),
            ("WHERE username IS NOT NULL", (user_desc, user_rows)),
        ])
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_connection_issues.invoke({"config": CONFIG}))
        assert out["max_sessions"] == 100
        assert out["total_sessions"] == 95
        assert out["active_sessions"] == 60
        assert out["session_usage_percent"] == 95.0
        assert out["is_near_limit"] is True
        assert any("90%" in w for w in out["warnings"])

    def test_health_check_full_score_path(self):
        inst = (_desc("INSTANCE_NAME", "HOST_NAME", "VERSION", "STATUS", "DATABASE_STATUS", "STARTUP_TIME"),
                [("ORCL", "h", "19c", "OPEN", "ACTIVE", "2024")])
        ts = (_desc("TABLESPACE_NAME", "TOTAL_BYTES", "FREE_BYTES", "USED_BYTES", "USAGE_PCT"),
              [("USERS", 1000, 100, 900, 90.0)])  # >85 -> warning -5
        sess = (_desc("TOTAL_SESSIONS", "ACTIVE_SESSIONS"), [(50, 10)])
        limit = (_desc("VALUE",), [("170",)])
        cache = (_desc("LOGICAL_READS", "PHYSICAL_READS"), [(1000, 100)])  # hit 90% <95 -> -15
        invalid = (_desc("INVALID_COUNT",), [(2,)])  # >0 -> -5
        fc = FakeConn([
            ("v$instance", inst),
            ("dba_data_files", ts),
            ("CASE WHEN status = 'ACTIVE'", sess),
            ("name = 'sessions'", limit),
            ("v$sysstat", cache),
            ("dba_objects", invalid),
        ])
        with _patch(diag, fc):
            out = json.loads(diag.check_database_health.invoke({"config": CONFIG}))
        # 100 -5(ts) -15(cache) -5(invalid) = 75 -> warning
        assert out["health_score"] == 75
        assert out["health_status"] == "warning"
        assert out["checks"]["instance"]["status"] == "ok"
        assert out["checks"]["tablespace"]["tablespaces"][0]["used_formatted"] == "900.00 B"
        assert out["checks"]["buffer_cache"]["hit_ratio"] == 90.0

    def test_health_check_instance_not_open(self):
        inst = (_desc("INSTANCE_NAME", "HOST_NAME", "VERSION", "STATUS", "DATABASE_STATUS", "STARTUP_TIME"),
                [("ORCL", "h", "19c", "MOUNTED", "ACTIVE", "2024")])
        empty = ([], [])
        fc = FakeConn([
            ("v$instance", inst),
            ("dba_data_files", ([], [])),
            ("CASE WHEN status = 'ACTIVE'", (_desc("TOTAL_SESSIONS", "ACTIVE_SESSIONS"), [(1, 0)])),
            ("name = 'sessions'", (_desc("VALUE",), [("170",)])),
            ("v$sysstat", (_desc("LOGICAL_READS", "PHYSICAL_READS"), [(100, 0)])),
            ("dba_objects", (_desc("INVALID_COUNT",), [(0,)])),
        ])
        with _patch(diag, fc):
            out = json.loads(diag.check_database_health.invoke({"config": CONFIG}))
        assert out["checks"]["instance"]["status"] == "critical"
        assert any("实例状态异常" in i for i in out["issues"])
        assert out["health_score"] == 70  # -30

    def test_dataguard_standby_with_lag(self):
        role = (_desc("DATABASE_ROLE", "PROTECTION_MODE", "PROTECTION_LEVEL", "SWITCHOVER_STATUS", "DATAGUARD_BROKER"),
                [("PHYSICAL STANDBY", "MAX PERFORMANCE", "MAX PERFORMANCE", "NOT ALLOWED", "ENABLED")])
        dg = (_desc("NAME", "VALUE", "TIME_COMPUTED", "DATUM_TIME"),
              [("transport lag", "+00 00:00:05", "t", "d"), ("apply lag", "+00 00:00:10", "t", "d")])
        fc = FakeConn([("v$database", role), ("v$dataguard_stats", dg)])
        with _patch(diag, fc):
            out = json.loads(diag.check_dataguard_status.invoke({"config": CONFIG}))
        assert out["database_role"] == "PHYSICAL STANDBY"
        assert out["transport_lag"] == "+00 00:00:05"
        assert out["dg_configured"] is True

    def test_dataguard_primary_with_destinations(self):
        role = (_desc("DATABASE_ROLE", "PROTECTION_MODE", "PROTECTION_LEVEL", "SWITCHOVER_STATUS", "DATAGUARD_BROKER"),
                [("PRIMARY", "MAX PERFORMANCE", "MAX PERFORMANCE", "TO STANDBY", "ENABLED")])
        dest = (_desc("DEST_ID", "DEST_NAME", "STATUS", "TYPE", "ERROR", "ARCHIVED_SEQ#", "APPLIED_SEQ#", "GAP_STATUS"),
                [(2, "LOG_ARCHIVE_DEST_2", "ERROR", "PHYSICAL", "ORA-16401", 100, 95, "NO GAP")])
        fc = FakeConn([("v$database", role), ("v$archive_dest_status", dest)])
        with _patch(diag, fc):
            out = json.loads(diag.check_dataguard_status.invoke({"config": CONFIG}))
        assert out["dg_configured"] is True
        assert out["has_dest_errors"] is True
        assert len(out["error_destinations"]) == 1

    def test_dataguard_no_database_rows(self):
        fc = FakeConn([("v$database", ([], []))])
        with _patch(diag, fc):
            out = json.loads(diag.check_dataguard_status.invoke({"config": CONFIG}))
        assert out["error"] == "无法查询v$database"


# ============================ resources ============================
class TestOracleResources:
    def test_current_database_info(self):
        db = (_desc("NAME", "DB_UNIQUE_NAME", "OPEN_MODE", "LOG_MODE"), [("ORCL", "ORCL", "READ WRITE", "ARCHIVELOG")])
        inst = (_desc("INSTANCE_NAME", "HOST_NAME", "STATUS", "STARTUP_TIME"), [("orcl1", "h", "OPEN", "2024")])
        ver = (_desc("BANNER",), [("Oracle Database 19c",)])
        fc = FakeConn([("v$database", db), ("v$instance", inst), ("v$version", ver)])
        with _patch(res, fc):
            out = json.loads(res.get_current_database_info.invoke({"config": CONFIG}))
        assert out["database_name"] == "ORCL"
        assert out["instance_name"] == "orcl1"
        assert out["version"] == "Oracle Database 19c"

    def test_list_tablespaces_usage(self):
        desc = _desc("TABLESPACE_NAME", "STATUS", "CONTENTS", "LOGGING", "TOTAL_BYTES", "FREE_BYTES")
        rows = [("USERS", "ONLINE", "PERMANENT", "LOGGING", 1024 * 1024, 256 * 1024)]  # used 75%
        fc = FakeConn([("dba_tablespaces", (desc, rows))])
        with _patch(res, fc):
            out = json.loads(res.list_oracle_tablespaces.invoke({"config": CONFIG}))
        ts = out["tablespaces"][0]
        assert ts["total_size"] == "1.00 MB"
        assert ts["usage_percentage"] == 75.0

    def test_list_tables_with_schema(self):
        desc = _desc("OWNER", "TABLE_NAME", "NUM_ROWS", "LAST_ANALYZED", "SIZE_BYTES")
        rows = [("APP", "ORDERS", 1000, "2024", 2 * 1024 * 1024)]
        fc = FakeConn([("all_tables", (desc, rows))])
        with _patch(res, fc):
            out = json.loads(res.list_oracle_tables.invoke({"db_schema": "app", "config": CONFIG}))
        assert out["schema"] == "app"
        assert out["tables"][0]["size"] == "2.00 MB"

    def test_list_tables_current_user(self):
        desc = _desc("OWNER", "TABLE_NAME", "NUM_ROWS", "LAST_ANALYZED", "SIZE_BYTES")
        rows = [("ME", "T", 1, "2024", 0)]
        fc = FakeConn([("user_tables", (desc, rows))])
        with _patch(res, fc):
            out = json.loads(res.list_oracle_tables.invoke({"config": CONFIG}))
        assert out["schema"] == "current_user"
        assert out["tables"][0]["size"] == "0.00 B"

    def test_list_indexes(self):
        desc = _desc("OWNER", "INDEX_NAME", "TABLE_NAME", "INDEX_TYPE", "UNIQUENESS", "STATUS", "NUM_ROWS",
                     "COLUMN_NAME", "COLUMN_POSITION")
        rows = [("APP", "IDX1", "T", "NORMAL", "UNIQUE", "VALID", 100, "ID", 1)]
        fc = FakeConn([("all_indexes", (desc, rows))])
        with _patch(res, fc):
            out = json.loads(res.list_oracle_indexes.invoke({"db_schema": "app", "table_name": "t", "config": CONFIG}))
        assert out["total_indexes"] == 1
        assert out["indexes"][0]["index_name"] == "IDX1"

    def test_get_table_structure_with_schema(self):
        col_desc = _desc("COLUMN_NAME", "DATA_TYPE", "DATA_LENGTH", "DATA_PRECISION", "DATA_SCALE", "NULLABLE",
                         "DATA_DEFAULT", "COLUMN_ID")
        col_rows = [("ID", "NUMBER", 22, 10, 0, "N", None, 1)]
        con_desc = _desc("CONSTRAINT_NAME", "CONSTRAINT_TYPE", "STATUS", "COLUMN_NAME", "POSITION")
        con_rows = [("PK_T", "P", "ENABLED", "ID", 1)]
        fc = FakeConn([("all_tab_columns", (col_desc, col_rows)), ("all_constraints", (con_desc, con_rows))])
        with _patch(res, fc):
            out = json.loads(res.get_table_structure.invoke({"table_name": "t", "db_schema": "app", "config": CONFIG}))
        assert out["columns"][0]["column_name"] == "ID"
        assert out["columns"][0]["data_default"] is None
        assert out["constraints"][0]["constraint_type"] == "P"

    def test_get_table_structure_current_user(self):
        col_desc = _desc("COLUMN_NAME", "DATA_TYPE", "DATA_LENGTH", "DATA_PRECISION", "DATA_SCALE", "NULLABLE",
                         "DATA_DEFAULT", "COLUMN_ID")
        col_rows = [("NAME", "VARCHAR2", 100, None, None, "Y", "'x'", 2)]
        fc = FakeConn([("user_tab_columns", (col_desc, col_rows)), ("user_constraints", ([], []))])
        with _patch(res, fc):
            out = json.loads(res.get_table_structure.invoke({"table_name": "t", "config": CONFIG}))
        assert out["columns"][0]["data_default"] == "'x'"
        assert out["schema"] == "current_user"

    def test_list_users_with_roles(self):
        u_desc = _desc("USERNAME", "ACCOUNT_STATUS", "DEFAULT_TABLESPACE", "CREATED")
        u_rows = [("APP", "OPEN", "USERS", "2024")]
        r_desc = _desc("GRANTEE", "GRANTED_ROLE")
        r_rows = [("APP", "CONNECT"), ("APP", "RESOURCE")]
        fc = FakeConn([("dba_users", (u_desc, u_rows)), ("dba_role_privs", (r_desc, r_rows))])
        with _patch(res, fc):
            out = json.loads(res.list_oracle_users.invoke({"config": CONFIG}))
        assert out["total_users"] == 1
        assert out["users"][0]["granted_roles"] == ["CONNECT", "RESOURCE"]

    def test_list_users_permission_fallback(self):
        fc = FakeConn([("dba_users", OracleError("ORA-00942")),
                       ("FROM DUAL", (_desc("USERNAME",), [("SCOTT",)]))])
        with _patch(res, fc):
            out = json.loads(res.list_oracle_users.invoke({"config": CONFIG}))
        assert "权限不足" in out["error"]
        assert out["current_user"] == "SCOTT"

    def test_get_database_config_formats_sizes(self):
        desc = _desc("NAME", "VALUE", "DISPLAY_VALUE", "DESCRIPTION")
        rows = [("sga_target", str(2 * 1024 ** 3), "2G", "SGA target"),
                ("optimizer_mode", "ALL_ROWS", "ALL_ROWS", "optimizer")]
        fc = FakeConn([("v$parameter", (desc, rows))])
        with _patch(res, fc):
            out = json.loads(res.get_database_config.invoke({"config": CONFIG}))
        assert out["settings"]["sga_target"]["formatted_size"] == "2.00 GB"
        assert "formatted_size" not in out["settings"]["optimizer_mode"]


# ============================ connection ============================
class TestOracleConnection:
    def test_normalize_defaults(self):
        out = conn.normalize_oracle_instance({})
        assert out["id"] == "oracle-1"
        assert out["port"] == 1521
        assert out["service_name"] == "ORCL"

    def test_normalize_bad_port(self):
        assert conn.normalize_oracle_instance({"port": "x"})["port"] == 1521

    def test_parse_instances(self):
        raw = json.dumps([{"name": "A", "host": "h"}, {"name": "B", "host": "h2"}])
        out = conn.parse_oracle_instances(raw)
        assert len(out) == 2
        assert out[1]["id"] == "oracle-2"

    def test_parse_instances_invalid(self):
        assert conn.parse_oracle_instances("{bad") == []
        assert conn.parse_oracle_instances(None) == []
        assert conn.parse_oracle_instances("123") == []

    def test_resolve(self):
        instances = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        assert conn.resolve_oracle_instance(instances, instance_id="b")["id"] == "b"
        assert conn.resolve_oracle_instance(instances, instance_name="A")["id"] == "a"
        assert conn.resolve_oracle_instance(instances, default_instance_id="b")["id"] == "b"
        assert conn.resolve_oracle_instance(instances)["id"] == "a"

    def test_resolve_not_found(self):
        with pytest.raises(ValueError):
            conn.resolve_oracle_instance([{"id": "a"}], instance_id="x")
        with pytest.raises(ValueError):
            conn.resolve_oracle_instance([])

    def test_build_config_from_instance_defaults(self):
        out = conn.build_oracle_config_from_instance({"host": "", "user": ""})
        assert out["host"] == "127.0.0.1"
        assert out["service_name"] == "ORCL"

    def test_create_connection_makes_dsn(self):
        with patch.object(conn.oracledb, "makedsn", return_value="DSN") as mk, \
             patch.object(conn.oracledb, "connect", return_value=MagicMock()) as cn:
            conn._create_oracle_connection({"host": "h", "port": 1521, "service_name": "S", "user": "u", "password": "p"})
        mk.assert_called_once_with("h", 1521, service_name="S")
        assert cn.call_args.kwargs["dsn"] == "DSN"
        assert cn.call_args.kwargs["user"] == "u"

    def test_get_connection_legacy(self):
        with patch.object(conn, "_create_oracle_connection", return_value=MagicMock()) as m:
            conn.get_oracle_connection(config=CONFIG)
        m.assert_called_once()

    def test_get_connection_instance_in_legacy_raises(self):
        with pytest.raises(ValueError):
            conn.get_oracle_connection(config=CONFIG, instance_name="X")

    def test_get_connection_multi_instance(self):
        cfg = {"configurable": {"oracle_instances": json.dumps([{"id": "a", "name": "A", "host": "ha"}])}}
        with patch.object(conn, "_create_oracle_connection", return_value=MagicMock()) as m:
            conn.get_oracle_connection(config=cfg, instance_name="A")
        m.assert_called_once()

    def test_adapter(self):
        a = conn.OracleCredentialAdapter()
        a.validate({"host": "h"})
        with pytest.raises(conn.CredentialValidationError):
            a.validate({"host": ""})
        assert a.get_display_name({}, 2) == "Oracle - 3"
        assert a.build_from_flat_config({"host": "fh"})["host"] == "fh"

    def test_build_normalized_multi(self):
        cfg = {"configurable": {"oracle_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}])}}
        n = conn.build_oracle_normalized_from_runnable(cfg)
        assert n["mode"] == "multi"
        assert len(n["items"]) == 2

    def test_build_normalized_single_select(self):
        cfg = {"configurable": {"oracle_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}])}}
        n = conn.build_oracle_normalized_from_runnable(cfg, instance_id="a")
        assert n["mode"] == "single"
        assert n["items"][0]["name"] == "A"

    def test_get_connection_from_item(self):
        item = {"config": {"host": "h", "port": 1521, "service_name": "S", "user": "u", "password": "p"}}
        with patch.object(conn, "_create_oracle_connection", return_value=MagicMock()) as m:
            conn.get_oracle_connection_from_item(item)
        m.assert_called_once()

    def test_test_instance_runs_select_dual(self):
        fake_cur = MagicMock()
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cur
        with patch.object(conn, "_create_oracle_connection", return_value=fake_conn):
            ok = conn.test_oracle_instance({"host": "h", "user": "u", "password": "p"})
        assert ok is True
        fake_cur.execute.assert_called_once_with("SELECT 1 FROM DUAL")
        fake_conn.close.assert_called_once()

    def test_test_instance_no_host(self):
        with pytest.raises(ValueError):
            conn.test_oracle_instance({"host": ""})

    def test_instances_prompt(self):
        cfg = {"oracle_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}]),
            "oracle_default_instance_id": "b"}
        prompt = conn.get_oracle_instances_prompt(cfg)
        assert "A, B" in prompt
        assert "「B」" in prompt
        assert conn.get_oracle_instances_prompt({}) == ""
