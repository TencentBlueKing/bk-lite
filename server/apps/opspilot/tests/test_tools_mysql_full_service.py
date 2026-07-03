"""MySQL @tool 工具集单元测试 (mysql/diagnostics|dynamic|resources|connection)。

mock 边界为 get_mysql_connection_from_item;FakeCursor 忽略 'SET SESSION TRANSACTION
READ ONLY' / 'USE `db`',按 SQL 关键字返回真实形态(description+tuple 行)。
execute_readonly_query 保持真实 zip→dict 逻辑。断言派生指标(健康分/会话使用率/缓存命中率)、
安全护栏(SELECT */写操作)、LIMIT 注入、敏感列过滤、performance_schema 异常翻译、
权限不足 fallback、Error 透出与连接关闭契约。不连真实 MySQL。
"""

import json
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest
from mysql.connector import Error

from apps.opspilot.metis.llm.tools.mysql import connection as conn  # noqa: E402
from apps.opspilot.metis.llm.tools.mysql import diagnostics as diag  # noqa: E402
from apps.opspilot.metis.llm.tools.mysql import dynamic as dyn  # noqa: E402
from apps.opspilot.metis.llm.tools.mysql import resources as res  # noqa: E402

CONFIG = {"configurable": {"host": "127.0.0.1", "port": 3306, "user": "root", "database": "appdb"}}


def _desc(*names):
    return [(n,) for n in names]


class FakeCursor:
    """忽略 SET/USE 控制语句, 按 SQL 子串分派 (description, rows)。

    matchers: list[(substr, payload)]; payload 为 (description, rows) 或 Error 实例(execute 抛出)。
    """

    def __init__(self, matchers):
        self._matchers = matchers
        self._desc = None
        self._rows = []
        self.closed = False
        self.executed = []

    @property
    def description(self):
        return self._desc

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if sql.startswith("SET ") or sql.startswith("USE "):
            return
        for substr, payload in self._matchers:
            if substr in sql:
                if isinstance(payload, Error):
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

    def cursor(self, dictionary=False):
        c = FakeCursor(self._matchers)
        self.cursors.append(c)
        return c

    def close(self):
        self.closed = True


def _patch(module, fc):
    return patch.object(module, "get_mysql_connection_from_item", return_value=fc)


# ============================ diagnostics ============================
class TestMysqlDiagnostics:
    def test_slow_queries_formats(self):
        desc = _desc("SCHEMA_NAME", "DIGEST_TEXT", "COUNT_STAR", "total_time_ms", "avg_time_ms",
                     "SUM_ROWS_EXAMINED", "SUM_ROWS_SENT")
        rows = [("app", "SELECT 1", 10, 5000, 500, 100, 50)]
        fc = FakeConn([("events_statements_summary_by_digest", (desc, rows))])
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_slow_queries.invoke({"config": CONFIG}))
        assert out["total_slow_queries"] == 1
        assert out["slow_queries"][0]["total_time_formatted"] == "5.00s"
        assert fc.closed is True

    def test_slow_queries_perf_schema_translated(self):
        fc = MagicMock()
        cur = MagicMock()
        cur.execute.side_effect = Error("Table 'performance_schema.x' doesn't exist")
        fc.cursor.return_value = cur
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_slow_queries.invoke({"config": CONFIG}))
        assert "performance_schema不可用" in out["error"]

    def test_lock_conflicts_80_path(self):
        desc = _desc("waiting_thread_id", "blocking_thread_id")
        rows = [(10, 11)]
        fc = FakeConn([("data_lock_waits", (desc, rows))])
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_lock_conflicts.invoke({"config": CONFIG}))
        assert out["has_conflicts"] is True
        assert out["total_lock_conflicts"] == 1

    def test_lock_conflicts_fallback_legacy(self):
        # 8.0 查询抛 Error -> fallback INNODB_LOCK_WAITS
        legacy_desc = _desc("waiting_trx_id", "blocking_trx_id")
        fc = FakeConn([("data_lock_waits", Error("unknown")), ("INNODB_LOCK_WAITS", (legacy_desc, [(1, 2)]))])
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_lock_conflicts.invoke({"config": CONFIG}))
        assert out["total_lock_conflicts"] == 1

    def test_connection_issues_warnings(self):
        status_desc = _desc("Variable_name", "Value")
        status_rows = [("Threads_connected", "95"), ("Threads_running", "5"),
                       ("Aborted_connects", "200"), ("Aborted_clients", "1"), ("Max_used_connections", "96")]
        var_rows = [("max_connections", "100"), ("wait_timeout", "28800")]
        fc = FakeConn([("SHOW GLOBAL STATUS", (status_desc, status_rows)),
                       ("SHOW GLOBAL VARIABLES", (status_desc, var_rows))])
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_connection_issues.invoke({"config": CONFIG}))
        assert out["max_connections"] == 100
        assert out["threads_connected"] == 95
        assert out["usage_percent"] == 95.0
        assert out["is_near_limit"] is True
        assert any("90%" in w for w in out["warnings"])
        assert any("异常断开" in w for w in out["warnings"])

    def test_health_check_scoring(self):
        status_desc = _desc("Variable_name", "Value")
        status_rows = [("Uptime", "1000"), ("Threads_connected", "95"), ("Threads_running", "3"),
                       ("Questions", "5000"), ("Innodb_buffer_pool_read_requests", "1000"),
                       ("Innodb_buffer_pool_reads", "100"), ("Slow_queries", "150"), ("Max_used_connections", "96")]
        var_rows = [("max_connections", "100")]
        fc = FakeConn([("SHOW GLOBAL STATUS", (status_desc, status_rows)),
                       ("SHOW GLOBAL VARIABLES", (status_desc, var_rows))])
        with _patch(diag, fc):
            out = json.loads(diag.check_database_health.invoke({"config": CONFIG}))
        # conn 95%(-20) + buffer hit 90%<95(-15) + slow>100(-10) = 55
        assert out["health_score"] == 55
        assert out["health_status"] == "critical"
        assert out["qps"] == 5.0  # 5000/1000
        assert out["buffer_pool_hit_ratio"] == 90.0

    def test_replication_lag_not_configured(self):
        fc = FakeConn([("SHOW REPLICA STATUS", (_desc("x"), []))])
        with _patch(diag, fc):
            out = json.loads(diag.check_replication_lag.invoke({"config": CONFIG}))
        assert out["has_replication"] is False

    def test_replication_lag_healthy(self):
        desc = _desc("Seconds_Behind_Source", "Replica_IO_Running", "Replica_SQL_Running", "Last_Error")
        rows = [(0, "Yes", "Yes", "")]
        fc = FakeConn([("SHOW REPLICA STATUS", (desc, rows))])
        with _patch(diag, fc):
            out = json.loads(diag.check_replication_lag.invoke({"config": CONFIG}))
        assert out["has_replication"] is True
        assert out["is_healthy"] is True
        assert out["io_running"] == "Yes"

    def test_replication_lag_fallback_slave(self):
        slave_desc = _desc("Seconds_Behind_Master", "Slave_IO_Running", "Slave_SQL_Running", "Last_Error")
        fc = FakeConn([("SHOW REPLICA STATUS", Error("unknown")),
                       ("SHOW SLAVE STATUS", (slave_desc, [(5, "Yes", "Yes", "")]))])
        with _patch(diag, fc):
            out = json.loads(diag.check_replication_lag.invoke({"config": CONFIG}))
        assert out["has_replication"] is True
        assert out["seconds_behind"] == 5

    def test_deadlocks_found(self):
        innodb_text = (
            "=====\n"
            "------------------------\n"
            "LATEST DETECTED DEADLOCK\n"
            "*** (1) TRANSACTION:\n"
            "deadlock detail line\n"
        )
        desc = _desc("Type", "Name", "Status")
        rows = [("InnoDB", "", innodb_text)]
        fc = FakeConn([("SHOW ENGINE INNODB STATUS", (desc, rows))])
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_deadlocks.invoke({"config": CONFIG}))
        assert out["deadlock_detected"] is True
        assert "LATEST DETECTED DEADLOCK" in out["deadlock_info"]

    def test_deadlocks_none(self):
        desc = _desc("Type", "Name", "Status")
        rows = [("InnoDB", "", "no deadlock here")]
        fc = FakeConn([("SHOW ENGINE INNODB STATUS", (desc, rows))])
        with _patch(diag, fc):
            out = json.loads(diag.diagnose_deadlocks.invoke({"config": CONFIG}))
        assert out["deadlock_detected"] is False

    def test_failed_queries(self):
        desc = _desc("SCHEMA_NAME", "DIGEST_TEXT", "COUNT_STAR", "SUM_ERRORS", "SUM_WARNINGS")
        rows = [("app", "INSERT", 10, 3, 1)]
        fc = FakeConn([("events_statements_summary_by_digest", (desc, rows))])
        with _patch(diag, fc):
            out = json.loads(diag.get_failed_queries.invoke({"config": CONFIG}))
        assert out["total_failed_queries"] == 1


# ============================ dynamic ============================
class TestMysqlDynamic:
    def test_table_schema_details(self):
        db_desc = _desc("db")
        col_desc = _desc("COLUMN_NAME", "ORDINAL_POSITION", "COLUMN_TYPE", "IS_NULLABLE",
                         "COLUMN_DEFAULT", "COLUMN_KEY", "EXTRA", "COLUMN_COMMENT")
        col_rows = [("id", 1, "int", "NO", None, "PRI", "auto_increment", "主键")]
        fk_desc = _desc("CONSTRAINT_NAME", "COLUMN_NAME", "foreign_schema", "foreign_table", "foreign_column")
        fc = FakeConn([("SELECT DATABASE()", (db_desc, [("appdb",)])),
                       ("information_schema.COLUMNS", (col_desc, col_rows)),
                       ("REFERENTIAL_CONSTRAINTS", (fk_desc, []))])
        with _patch(dyn, fc):
            out = json.loads(dyn.get_table_schema_details.invoke({"table_name": "users", "config": CONFIG}))
        assert out["database"] == "appdb"
        assert out["columns"][0]["COLUMN_NAME"] == "id"

    def test_table_schema_details_no_columns(self):
        fc = FakeConn([("SELECT DATABASE()", (_desc("db"), [("appdb",)])),
                       ("information_schema.COLUMNS", (_desc("COLUMN_NAME"), []))])
        with _patch(dyn, fc):
            out = json.loads(dyn.get_table_schema_details.invoke({"table_name": "nope", "config": CONFIG}))
        assert "不存在" in out["error"]

    def test_search_tables(self):
        t_desc = _desc("TABLE_NAME", "TABLE_COMMENT", "TABLE_ROWS")
        c_desc = _desc("TABLE_NAME", "COLUMN_NAME", "COLUMN_TYPE", "COLUMN_COMMENT")
        fc = FakeConn([("information_schema.TABLES", (t_desc, [("users", "用户表", 100)])),
                       ("information_schema.COLUMNS", (c_desc, [("users", "user_id", "int", "")]))])
        with _patch(dyn, fc):
            out = json.loads(dyn.search_tables_by_keyword.invoke({"keyword": "user", "database": "appdb", "config": CONFIG}))
        assert out["matching_tables"][0]["TABLE_NAME"] == "users"
        assert out["matching_columns"][0]["COLUMN_NAME"] == "user_id"

    def test_execute_safe_select_rejects_star(self):
        out = json.loads(dyn.execute_safe_select.invoke({"query": "SELECT * FROM users", "config": CONFIG}))
        assert "SELECT *" in out["error"]

    def test_execute_safe_select_unsafe(self):
        out = json.loads(dyn.execute_safe_select.invoke({"query": "DELETE FROM users", "config": CONFIG}))
        assert "SQL安全检查失败" in out["error"]

    def test_execute_safe_select_injects_limit(self):
        db_desc = _desc("db")
        data_desc = _desc("id", "name")
        fc = FakeConn([("SELECT DATABASE()", (db_desc, [("appdb",)])),
                       ("SELECT id, name FROM users", (data_desc, [(1, "a")]))])
        with _patch(dyn, fc):
            out = json.loads(dyn.execute_safe_select.invoke({"query": "SELECT id, name FROM users", "config": CONFIG}))
        assert out["success"] is True
        assert "LIMIT 100" in out["sql"]

    def test_explain_query_plan(self):
        db_desc = _desc("db")
        plan_desc = _desc("id", "select_type", "table", "type", "rows")
        fc = FakeConn([("SELECT DATABASE()", (db_desc, [("appdb",)])),
                       ("EXPLAIN", (plan_desc, [(1, "SIMPLE", "users", "ALL", 100)]))])
        with _patch(dyn, fc):
            out = json.loads(dyn.explain_query_plan.invoke({"query": "SELECT id FROM users", "config": CONFIG}))
        assert out["success"] is True
        assert out["execution_plan"][0]["table"] == "users"

    def test_explain_query_plan_unsafe(self):
        out = json.loads(dyn.explain_query_plan.invoke({"query": "DROP TABLE users", "config": CONFIG}))
        assert "SQL安全检查失败" in out["error"]

    def test_get_sample_data_invalid_table(self):
        out = json.loads(dyn.get_sample_data.invoke({"table_name": "bad-name", "config": CONFIG}))
        assert "无效的表名" in out["error"]

    def test_get_sample_data_filters_sensitive_columns(self):
        db_desc = _desc("db")
        col_desc = _desc("COLUMN_NAME")
        col_rows = [("id",), ("name",), ("password",)]
        data_desc = _desc("id", "name")
        fc = FakeConn([("SELECT DATABASE()", (db_desc, [("appdb",)])),
                       ("information_schema.COLUMNS", (col_desc, col_rows)),
                       ("FROM `appdb`.`users`", (data_desc, [(1, "a")]))])
        with _patch(dyn, fc):
            out = json.loads(dyn.get_sample_data.invoke({"table_name": "users", "config": CONFIG}))
        assert out["success"] is True
        assert "password" not in out["columns"]
        assert "id" in out["columns"]

    def test_execute_safe_select_batch(self):
        db_desc = _desc("db")
        data_desc = _desc("id")
        fc = FakeConn([("SELECT DATABASE()", (db_desc, [("appdb",)])),
                       ("SELECT id FROM users", (data_desc, [(1,)]))])
        with _patch(dyn, fc):
            out = json.loads(dyn.execute_safe_select_batch.invoke(
                {"queries": ["SELECT id FROM users", "SELECT * FROM t", "DELETE FROM t"], "config": CONFIG}))
        assert out["total"] == 3
        assert out["succeeded"] == 1
        assert out["failed"] == 2


# ============================ resources ============================
class TestMysqlResources:
    def test_current_database_info(self):
        info_desc = _desc("version", "hostname", "port", "datadir", "character_set_server",
                          "collation_server", "default_storage_engine")
        info_rows = [("8.0.30", "h", 3306, "/data", "utf8mb4", "utf8mb4_general_ci", "InnoDB")]
        up_desc = _desc("uptime_seconds")
        fc = FakeConn([("VERSION() AS version", (info_desc, info_rows)),
                       ("global_status", (up_desc, [("1000",)]))])
        with _patch(res, fc):
            out = json.loads(res.get_current_database_info.invoke({"config": CONFIG}))
        assert out["version"] == "8.0.30"
        assert out["uptime_seconds"] == "1000"

    def test_list_databases_formats_size(self):
        desc = _desc("SCHEMA_NAME", "DEFAULT_CHARACTER_SET_NAME", "DEFAULT_COLLATION_NAME", "size_bytes")
        rows = [("appdb", "utf8mb4", "utf8mb4_ci", 1048576)]
        fc = FakeConn([("information_schema.SCHEMATA", (desc, rows))])
        with _patch(res, fc):
            out = json.loads(res.list_mysql_databases.invoke({"config": CONFIG}))
        assert out["databases"][0]["size"] == "1.00 MB"

    def test_list_tables(self):
        desc = _desc("TABLE_NAME", "ENGINE", "TABLE_ROWS", "DATA_LENGTH", "INDEX_LENGTH", "TABLE_COMMENT")
        rows = [("orders", "InnoDB", 1000, 1048576, 524288, "订单")]
        fc = FakeConn([("information_schema.TABLES", (desc, rows))])
        with _patch(res, fc):
            out = json.loads(res.list_mysql_tables.invoke({"database": "shop", "config": CONFIG}))
        assert out["database"] == "shop"
        assert out["tables"][0]["total_size"] == "1.50 MB"

    def test_list_indexes(self):
        desc = _desc("INDEX_NAME", "COLUMN_NAME", "NON_UNIQUE", "SEQ_IN_INDEX", "INDEX_TYPE", "CARDINALITY")
        rows = [("PRIMARY", "id", 0, 1, "BTREE", 1000)]
        fc = FakeConn([("information_schema.STATISTICS", (desc, rows))])
        with _patch(res, fc):
            out = json.loads(res.list_mysql_indexes.invoke({"table_name": "orders", "database": "shop", "config": CONFIG}))
        assert out["indexes"][0]["index_name"] == "PRIMARY"

    def test_list_schemas(self):
        desc = _desc("SCHEMA_NAME", "DEFAULT_CHARACTER_SET_NAME", "DEFAULT_COLLATION_NAME")
        rows = [("appdb", "utf8mb4", "utf8mb4_ci")]
        fc = FakeConn([("information_schema.SCHEMATA", (desc, rows))])
        with _patch(res, fc):
            out = json.loads(res.list_mysql_schemas.invoke({"config": CONFIG}))
        assert out["total_schemas"] == 1

    def test_get_table_structure(self):
        col_desc = _desc("COLUMN_NAME", "COLUMN_TYPE", "IS_NULLABLE", "COLUMN_KEY", "COLUMN_DEFAULT", "EXTRA", "COLUMN_COMMENT")
        idx_desc = _desc("INDEX_NAME", "COLUMN_NAME", "NON_UNIQUE", "SEQ_IN_INDEX", "INDEX_TYPE")
        con_desc = _desc("CONSTRAINT_NAME", "CONSTRAINT_TYPE", "COLUMN_NAME", "REFERENCED_TABLE_NAME", "REFERENCED_COLUMN_NAME")
        fc = FakeConn([("information_schema.COLUMNS", (col_desc, [("id", "int", "NO", "PRI", None, "", "")])),
                       ("information_schema.STATISTICS", (idx_desc, [("PRIMARY", "id", 0, 1, "BTREE")])),
                       ("TABLE_CONSTRAINTS", (con_desc, [("PRIMARY", "PRIMARY KEY", "id", None, None)]))])
        with _patch(res, fc):
            out = json.loads(res.get_table_structure.invoke({"table_name": "orders", "database": "shop", "config": CONFIG}))
        assert out["columns"][0]["COLUMN_NAME"] == "id"
        assert out["constraints"][0]["CONSTRAINT_TYPE"] == "PRIMARY KEY"

    def test_list_users(self):
        desc = _desc("Host", "User", "Select_priv", "Insert_priv", "Update_priv", "Delete_priv", "Grant_priv", "Super_priv")
        rows = [("%", "app", "Y", "Y", "N", "N", "N", "N")]
        fc = FakeConn([("mysql.user", (desc, rows))])
        with _patch(res, fc):
            out = json.loads(res.list_mysql_users.invoke({"config": CONFIG}))
        assert out["users"][0]["user"] == "app"

    def test_list_users_permission_fallback(self):
        fc = FakeConn([("mysql.user", Error("denied")),
                       ("CURRENT_USER()", (_desc("current_user"), [("root@localhost",)]))])
        with _patch(res, fc):
            out = json.loads(res.list_mysql_users.invoke({"config": CONFIG}))
        assert "权限不足" in out["error"]
        assert out["current_user"] == "root@localhost"

    def test_get_database_config_formats_sizes(self):
        # 每个 SHOW GLOBAL VARIABLES LIKE 返回 (Variable_name, Value)
        def matcher_for(name, value):
            return (_desc("Variable_name", "Value"), [(name, value)])

        # 让 FakeCursor 对所有 SHOW GLOBAL VARIABLES 返回基于 params 的值
        class CfgCursor(FakeCursor):
            def execute(self, sql, params=None):
                self.executed.append((sql, params))
                if "SHOW GLOBAL VARIABLES" in sql and params:
                    name = params[0]
                    val = {"innodb_buffer_pool_size": str(2 * 1024 ** 3), "max_connections": "200"}.get(name, "x")
                    self._desc = _desc("Variable_name", "Value")
                    self._rows = [(name, val)]
                else:
                    self._desc, self._rows = [], []

        class CfgConn(FakeConn):
            def cursor(self, dictionary=False):
                c = CfgCursor([])
                self.cursors.append(c)
                return c

        with _patch(res, CfgConn([])):
            out = json.loads(res.get_database_config.invoke({"config": CONFIG}))
        assert out["settings"]["innodb_buffer_pool_size"]["display"] == "2.00 GB"
        assert out["settings"]["max_connections"]["value"] == "200"

    def test_resource_error(self):
        fc = MagicMock()
        fc.cursor.side_effect = Error("boom")
        with _patch(res, fc):
            out = json.loads(res.list_mysql_databases.invoke({"config": CONFIG}))
        assert out["error"] == "boom"
        fc.close.assert_called_once()


# ============================ connection ============================
class TestMysqlConnection:
    def test_normalize_defaults(self):
        out = conn.normalize_mysql_instance({})
        assert out["id"] == "mysql-1"
        assert out["port"] == 3306

    def test_parse_instances(self):
        raw = json.dumps([{"name": "A", "host": "h"}, {"name": "B", "host": "h2"}])
        out = conn.parse_mysql_instances(raw)
        assert len(out) == 2
        assert out[1]["id"] == "mysql-2"

    def test_parse_instances_invalid(self):
        assert conn.parse_mysql_instances("{bad") == []
        assert conn.parse_mysql_instances(None) == []

    def test_resolve(self):
        instances = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        assert conn.resolve_mysql_instance(instances, instance_id="b")["id"] == "b"
        assert conn.resolve_mysql_instance(instances, instance_name="A")["id"] == "a"
        assert conn.resolve_mysql_instance(instances, default_instance_id="b")["id"] == "b"
        assert conn.resolve_mysql_instance(instances)["id"] == "a"

    def test_resolve_not_found(self):
        with pytest.raises(ValueError):
            conn.resolve_mysql_instance([{"id": "a"}], instance_id="x")
        with pytest.raises(ValueError):
            conn.resolve_mysql_instance([])

    def test_build_normalized_multi(self):
        cfg = {"configurable": {"mysql_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}])}}
        n = conn.build_mysql_normalized_from_runnable(cfg)
        assert n["mode"] == "multi"
        assert len(n["items"]) == 2

    def test_build_normalized_single_select(self):
        cfg = {"configurable": {"mysql_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}])}}
        n = conn.build_mysql_normalized_from_runnable(cfg, instance_name="B")
        assert n["mode"] == "single"
        assert n["items"][0]["name"] == "B"

    def test_get_connection_from_item(self):
        item = {"config": {"host": "h", "port": 3306, "database": "d", "user": "u", "password": "p"}}
        fake = MagicMock()
        with patch.object(conn, "connect", return_value=fake) as m:
            conn.get_mysql_connection_from_item(item)
        m.assert_called_once()

    def test_instances_prompt(self):
        cfg = {"mysql_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}]),
            "mysql_default_instance_id": "b"}
        prompt = conn.get_mysql_instances_prompt(cfg)
        assert "A, B" in prompt
        assert "「B」" in prompt
        assert conn.get_mysql_instances_prompt({}) == ""
