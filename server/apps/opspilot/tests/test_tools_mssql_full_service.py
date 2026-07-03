"""MSSQL @tool 工具集单元测试 (mssql/diagnostics|dynamic|resources|connection)。

mock 边界:
- diagnostics/dynamic/resources: 模块内 execute_readonly_query(真实 DB 边界, 内部走
  pyodbc.connect),用按 SQL 关键字分派的 side_effect 返回真实形态 dict 行。
- connection: pyodbc.connect / pyodbc.drivers 打桩,验证连接串构造与实例解析。

断言工具产出的结构化 JSON、派生指标(健康分/usage_percent/碎片大小格式化)、安全护栏
(SELECT * / 敏感字段 / WITH 须 TOP / 无约束大范围扫描)、TOP 注入改写、异常脱敏透出。
不连真实 MSSQL。

pyodbc 在导入 mssql 子模块时被加载;缺 unixodbc 时整文件跳过(本机已装 unixodbc)。
"""

import json
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest

pytest.importorskip("pyodbc", reason="pyodbc/unixodbc 未安装,跳过 MSSQL 工具测试")

from apps.opspilot.metis.llm.tools.mssql import connection as conn  # noqa: E402
from apps.opspilot.metis.llm.tools.mssql import diagnostics as diag  # noqa: E402
from apps.opspilot.metis.llm.tools.mssql import dynamic as dyn  # noqa: E402
from apps.opspilot.metis.llm.tools.mssql import resources as res  # noqa: E402

CONFIG = {"configurable": {"host": "127.0.0.1", "port": 1433, "user": "sa", "password": "p", "database": "appdb"}}


def _dispatch(matchers):
    """返回一个 execute_readonly_query side_effect: 按 SQL 子串匹配返回 dict 行列表。

    matchers: list[(substr, rows)] —— 命中第一个包含 substr 的 SQL 即返回对应 rows。
    """

    def _impl(query, params=None, config=None, database=None):
        for substr, rows in matchers:
            if substr in query:
                return rows
        return []

    return _impl


# ============================ diagnostics ============================
class TestMssqlDiagnostics:
    def test_slow_queries_formats_time_fields(self):
        rows = [
            {
                "query": "SELECT 1",
                "execution_count": 10,
                "total_time_ms": 5000,
                "avg_time_ms": 500,
                "max_time_ms": 1200,
                "total_cpu_time_ms": 400,
                "total_reads": 100,
                "total_writes": 5,
                "creation_time": "2024-01-01",
                "last_execution_time": "2024-06-01",
            }
        ]
        with patch.object(diag, "execute_readonly_query", _dispatch([("dm_exec_query_stats", rows)])):
            out = json.loads(diag.diagnose_slow_queries.invoke({"threshold_ms": 1000, "config": CONFIG}))
        assert out["threshold_ms"] == 1000
        assert out["total_slow_queries"] == 1
        q = out["slow_queries"][0]
        assert q["creation_time"] == "2024-01-01"
        # safe_json_dumps 富化: total_time_ms -> *_formatted/_display
        assert q["total_time_formatted"] == "5.00s"
        assert q["avg_time_formatted"] == "500.00ms"

    def test_slow_queries_error_sanitized(self):
        with patch.object(diag, "execute_readonly_query", side_effect=RuntimeError("boom")):
            out = json.loads(diag.diagnose_slow_queries.invoke({"config": CONFIG}))
        assert out["error"] == "boom"

    def test_lock_conflicts_has_conflicts_flag(self):
        rows = [{"blocked_session_id": 53, "blocking_session_id": 51, "wait_time_ms": 2000}]
        with patch.object(diag, "execute_readonly_query", _dispatch([("dm_exec_requests", rows)])):
            out = json.loads(diag.diagnose_lock_conflicts.invoke({"config": CONFIG}))
        assert out["total_blocked_queries"] == 1
        assert out["has_conflicts"] is True

    def test_connection_issues_usage_percent_and_near_limit(self):
        # max user connections=0 -> 回退 32767; 但 current_connections=summed
        matchers = [
            ("user connections", [{"max_connections": 100}]),
            # long_running_query 含 dm_exec_requests, 须先于 connections_query 的 GROUP BY 匹配
            ("WHERE r.total_elapsed_time", [{"session_id": 5, "login_name": "u", "database_name": "appdb",
                                             "status": "running", "query": "SELECT 1", "duration_ms": 400000,
                                             "start_time": "2024-06-01"}]),
            ("GROUP BY database_id", [
                {"database_name": "appdb", "login_name": "u", "status": "running", "connection_count": 95,
                 "idle_count": 0, "active_count": 95, "suspended_count": 0},
            ]),
        ]
        with patch.object(diag, "execute_readonly_query", _dispatch(matchers)):
            out = json.loads(diag.diagnose_connection_issues.invoke({"config": CONFIG}))
        assert out["max_connections"] == 100
        assert out["current_connections"] == 95
        assert out["usage_percent"] == 95.0
        assert out["is_near_limit"] is True
        assert out["long_running_queries"][0]["start_time"] == "2024-06-01"

    def test_health_check_scoring_with_issues(self):
        stats = [{
            "max_connections": 100,
            "current_connections": 95,  # 95% -> -20
            "active_queries": 2,
            "suspended_queries": 1,
            "blocked_queries": 3,  # -15
            "long_running_queries": 1,  # -15
        }]
        dbs = [{"database_name": "appdb", "state": "ONLINE", "user_access": "MULTI_USER", "recovery_model": "FULL"},
               {"database_name": "old", "state": "OFFLINE", "user_access": "MULTI_USER", "recovery_model": "SIMPLE"}]
        disk = [{"database_name": "appdb", "file_type": "ROWS", "logical_name": "d", "physical_name": "/x",
                 "size_mb": 100, "used_mb": 60, "free_mb": 40}]
        matchers = [("max server memory", []), ("user connections", stats), ("sys.databases", dbs),
                    ("master_files", disk)]
        # stats_query 含 'user connections' 子串; db_status_query 含 'sys.databases'; disk 含 master_files
        with patch.object(diag, "execute_readonly_query", _dispatch([
            ("FROM sys.databases", dbs),
            ("master_files", disk),
            ("user connections", stats),
        ])):
            out = json.loads(diag.check_database_health.invoke({"config": CONFIG}))
        # 95% conn(-20) + blocked(-15) + long_running(-15) + offline db(-20) = 30
        assert out["health_score"] == 30
        assert out["health_status"] == "critical"
        assert any("被阻塞" in i for i in out["issues"])
        assert any("非ONLINE" in i for i in out["issues"])
        # disk 富化: used_mb -> used_formatted
        assert out["disk_space"][0]["used_formatted"] == "60.00 MB"

    def test_replication_lag_hadr_disabled(self):
        with patch.object(diag, "execute_readonly_query", _dispatch([("IsHadrEnabled", [{"is_hadr_enabled": 0}])])):
            out = json.loads(diag.check_replication_lag.invoke({"config": CONFIG}))
        assert out["has_replication"] is False
        assert "HADR" in out["message"]

    def test_replication_lag_hadr_enabled_with_replicas(self):
        matchers = [
            ("IsHadrEnabled", [{"is_hadr_enabled": 1}]),
            ("availability_groups", [{"availability_group": "ag1", "role": "PRIMARY",
                                      "replica_server_name": "node1", "sync_health": "HEALTHY",
                                      "log_send_queue_kb": 0, "redo_queue_kb": 0, "last_commit_time": "2024"}]),
        ]
        with patch.object(diag, "execute_readonly_query", _dispatch(matchers)):
            out = json.loads(diag.check_replication_lag.invoke({"config": CONFIG}))
        assert out["has_replication"] is True
        assert out["replica_count"] == 1
        assert out["replicas"][0]["last_commit_time"] == "2024"

    def test_deadlocks_none(self):
        with patch.object(diag, "execute_readonly_query", _dispatch([("xml_deadlock_report", [])])):
            out = json.loads(diag.diagnose_deadlocks.invoke({"config": CONFIG}))
        assert out["deadlock_count"] == 0

    def test_deadlocks_found_truncated_graph(self):
        rows = [{"deadlock_time": "2024-06-01", "deadlock_graph": "X" * 5000}]
        with patch.object(diag, "execute_readonly_query", _dispatch([("xml_deadlock_report", rows)])):
            out = json.loads(diag.diagnose_deadlocks.invoke({"config": CONFIG}))
        assert out["deadlock_count"] == 1
        assert len(out["deadlocks"][0]["deadlock_graph"]) == 2000

    def test_failed_queries(self):
        matchers = [
            ("fn_readerrorlog", [{"error_time": "2024-06-01", "process_info": "spid1", "error_message": "err"}]),
            ("dm_db_index_usage_stats", [{"database_name": "appdb", "total_reads": 100, "total_writes": 5}]),
        ]
        with patch.object(diag, "execute_readonly_query", _dispatch(matchers)):
            out = json.loads(diag.get_failed_queries.invoke({"config": CONFIG}))
        assert out["error_count"] == 1
        assert out["recent_errors"][0]["error_time"] == "2024-06-01"
        assert out["database_stats"][0]["database_name"] == "appdb"


# ============================ dynamic ============================
class TestMssqlDynamic:
    def test_table_schema_details_not_found(self):
        with patch.object(dyn, "execute_readonly_query", _dispatch([("sys.tables", [])])):
            out = json.loads(dyn.get_table_schema_details.invoke({"table_name": "t", "config": CONFIG}))
        assert "不存在" in out["error"]

    def test_table_schema_details_full(self):
        info = [{"table_name": "t", "schema_name": "dbo", "estimated_rows": 100, "total_size_bytes": 1048576}]
        cols = [{"column_name": "id", "data_type": "int", "is_primary_key": 1}]
        idx = [{"index_name": "pk", "is_unique": 1, "is_primary_key": 1, "columns": "id"}]
        fks = [{"constraint_name": "fk", "column_name": "uid", "foreign_table": "u", "foreign_column": "id"}]
        # 注意各查询都含 'sys.', 用更精确子串区分
        matchers = [
            ("p.rows as estimated_rows", info),
            ("column_id as column_position", cols),
            ("i.is_unique", idx),
            ("foreign_keys fk", fks),
        ]
        with patch.object(dyn, "execute_readonly_query", _dispatch(matchers)):
            out = json.loads(dyn.get_table_schema_details.invoke({"table_name": "t", "config": CONFIG}))
        assert out["table_info"]["total_size"] == "1.00 MB"
        assert out["columns"][0]["column_name"] == "id"
        assert out["foreign_keys"][0]["foreign_table"] == "u"

    def test_search_tables_by_keyword(self):
        rows = [{"schema_name": "dbo", "table_name": "users", "estimated_rows": 10, "matching_columns": "id, name"}]
        with patch.object(dyn, "execute_readonly_query", _dispatch([("sys.tables", rows)])):
            out = json.loads(dyn.search_tables_by_keyword.invoke({"keyword": "user", "config": CONFIG}))
        assert out["keyword"] == "user"
        assert out["total_matches"] == 1

    def test_execute_safe_select_rejects_star(self):
        out = json.loads(dyn.execute_safe_select.invoke({"sql": "SELECT * FROM dbo.users", "config": CONFIG}))
        assert "SELECT *" in out["error"]

    def test_execute_safe_select_rejects_sensitive(self):
        out = json.loads(dyn.execute_safe_select.invoke({"sql": "SELECT id, password FROM dbo.users", "config": CONFIG}))
        assert "敏感字段" in out["error"]

    def test_execute_safe_select_injects_top(self):
        captured = {}

        def _impl(query, params=None, config=None, database=None):
            captured["sql"] = query
            return [{"id": 1, "name": "a"}]

        with patch.object(dyn, "execute_readonly_query", _impl):
            out = json.loads(dyn.execute_safe_select.invoke({"sql": "SELECT id, name FROM dbo.users WHERE id=1", "limit": 50, "config": CONFIG}))
        assert out["success"] is True
        assert out["row_count"] == 1
        assert out["limit"] == 50
        assert "TOP 50" in captured["sql"]

    def test_execute_safe_select_caps_existing_top(self):
        captured = {}

        def _impl(query, params=None, config=None, database=None):
            captured["sql"] = query
            return []

        with patch.object(dyn, "execute_readonly_query", _impl):
            dyn.execute_safe_select.invoke({"sql": "SELECT TOP 5000 id FROM dbo.t WHERE id=1", "limit": 100, "config": CONFIG})
        assert "TOP 100" in captured["sql"]
        assert "TOP 5000" not in captured["sql"]

    def test_execute_fallback_with_query_requires_top(self):
        out = json.loads(dyn.execute_fallback_readonly_sql.invoke({"sql": "WITH cte AS (SELECT id FROM t) SELECT id FROM cte", "config": CONFIG}))
        assert out["guardrail"] == "with_query_requires_top"

    def test_execute_fallback_broad_scan_blocked(self):
        out = json.loads(dyn.execute_fallback_readonly_sql.invoke({"sql": "SELECT id FROM dbo.users", "config": CONFIG}))
        # SELECT 无 TOP/WHERE -> 先注入 TOP? broad-scan 检测在注入前, 但本句无约束应被拦
        # 实际: _is_broad_select_without_constraints 检测 (无 top/where/join...) -> 命中
        assert out.get("guardrail") == "broad_scan_without_top"

    def test_execute_fallback_success_injects_top(self):
        captured = {}

        def _impl(query, params=None, config=None, database=None):
            captured["sql"] = query
            return [{"id": 1}]

        with patch.object(dyn, "execute_readonly_query", _impl):
            out = json.loads(dyn.execute_fallback_readonly_sql.invoke({"sql": "SELECT id FROM dbo.users WHERE id=1", "config": CONFIG}))
        assert out["mode"] == "fallback_readonly"
        assert out["success"] is True
        assert "TOP 100" in captured["sql"]

    def test_explain_query_plan_cached(self):
        rows = [{"execution_count": 5, "total_cpu_time_ms": 10, "query_text": "SELECT id FROM t"}]
        with patch.object(dyn, "execute_readonly_query", _dispatch([("dm_exec_query_stats", rows)])):
            out = json.loads(dyn.explain_query_plan.invoke({"sql": "SELECT id FROM dbo.t WHERE id=1", "config": CONFIG}))
        assert out["success"] is True
        assert out["cached_plan_stats"]["execution_count"] == 5

    def test_explain_query_plan_no_cache(self):
        with patch.object(dyn, "execute_readonly_query", _dispatch([("dm_exec_query_stats", [])])):
            out = json.loads(dyn.explain_query_plan.invoke({"sql": "SELECT id FROM dbo.t WHERE id=1", "config": CONFIG}))
        assert out["success"] is True
        assert "未找到" in out["message"]

    def test_get_sample_data_requires_columns(self):
        out = json.loads(dyn.get_sample_data.invoke({"table_name": "users", "config": CONFIG}))
        assert "必须明确指定" in out["error"]

    def test_get_sample_data_rejects_sensitive_columns(self):
        out = json.loads(dyn.get_sample_data.invoke({"table_name": "users", "columns": "id,token", "config": CONFIG}))
        assert "敏感字段" in out["error"]

    def test_get_sample_data_invalid_table(self):
        out = json.loads(dyn.get_sample_data.invoke({"table_name": "bad-name", "columns": "id", "config": CONFIG}))
        assert out["error"] == "无效的表名"

    def test_get_sample_data_success(self):
        with patch.object(dyn, "execute_readonly_query", _dispatch([("FROM dbo.users", [{"id": 1, "name": "a"}])])):
            out = json.loads(dyn.get_sample_data.invoke({"table_name": "users", "columns": "id,name", "limit": 5, "config": CONFIG}))
        assert out["success"] is True
        assert out["table"] == "dbo.users"
        assert out["row_count"] == 1

    def test_execute_safe_select_batch(self):
        # batch 走 get_mssql_connection_from_item -> conn.execute
        fake_cursor = MagicMock()
        fake_cursor.description = [("id",), ("name",)]
        fake_cursor.fetchall.return_value = [(1, "a")]
        fake_conn = MagicMock()
        fake_conn.execute.return_value = fake_cursor
        with patch.object(dyn, "validate_sql_safety", return_value=(True, "")), \
             patch("apps.opspilot.metis.llm.tools.mssql.connection.get_mssql_connection_from_item", return_value=fake_conn):
            out = json.loads(dyn.execute_safe_select_batch.invoke(
                {"queries": ["SELECT id, name FROM dbo.users WHERE id=1"], "config": CONFIG}))
        assert out["total"] == 1
        assert out["succeeded"] == 1
        assert out["results"][0]["ok"] is True
        fake_conn.close.assert_called_once()

    def test_execute_safe_select_batch_unsafe_query(self):
        with patch.object(dyn, "validate_sql_safety", return_value=(False, "禁止写操作")):
            out = json.loads(dyn.execute_safe_select_batch.invoke({"queries": ["DELETE FROM t"], "config": CONFIG}))
        assert out["failed"] == 1
        assert out["succeeded"] == 0


# ============================ resources ============================
class TestMssqlResources:
    def test_current_database_info(self):
        rows = [{"database_name": "appdb", "username": "sa", "sql_version": "v", "server_name": "srv",
                 "edition": "Std", "product_version": "16.0"}]
        with patch.object(res, "execute_readonly_query", _dispatch([("DB_NAME()", rows)])):
            out = json.loads(res.get_current_database_info.invoke({"config": CONFIG}))
        assert out["current_database"] == "appdb"
        assert out["edition"] == "Std"

    def test_list_databases_formats_size(self):
        rows = [{"name": "appdb", "database_id": 5, "state": "ONLINE", "recovery_model": "FULL",
                 "collation": "Latin1", "size_bytes": 2 * 1024 * 1024 * 1024}]
        with patch.object(res, "execute_readonly_query", _dispatch([("sys.databases", rows)])):
            out = json.loads(res.list_mssql_databases.invoke({"config": CONFIG}))
        assert out["total_databases"] == 1
        assert out["databases"][0]["size"] == "2.00 GB"

    def test_list_tables_formats_sizes(self):
        rows = [{"table_name": "orders", "schema_name": "dbo", "row_count": 1000,
                 "total_size_bytes": 1048576, "used_size_bytes": 524288, "index_count": 2}]
        with patch.object(res, "execute_readonly_query", _dispatch([("sys.tables", rows)])):
            out = json.loads(res.list_mssql_tables.invoke({"database": "shop", "config": CONFIG}))
        assert out["database"] == "shop"
        assert out["tables"][0]["total_size"] == "1.00 MB"
        assert out["tables"][0]["used_size"] == "512.00 KB"

    def test_list_indexes_with_table_marks_unused(self):
        rows = [{"index_name": "idx_a", "table_name": "t", "index_type": "NONCLUSTERED",
                 "is_unique": 0, "is_primary_key": 0, "size_bytes": 1024, "columns": "c1",
                 "index_usage": 0, "index_updates": 5}]
        with patch.object(res, "execute_readonly_query", _dispatch([("sys.indexes", rows)])):
            out = json.loads(res.list_mssql_indexes.invoke({"table": "t", "config": CONFIG}))
        assert out["table"] == "t"
        assert out["indexes"][0]["is_unused"] is True
        assert out["indexes"][0]["size"] == "1.00 KB"

    def test_list_indexes_without_table(self):
        rows = [{"index_name": "idx_b", "table_name": "t2", "index_type": "CLUSTERED",
                 "is_unique": 1, "is_primary_key": 1, "size_bytes": 2048, "index_usage": 10, "index_updates": 1}]
        with patch.object(res, "execute_readonly_query", _dispatch([("sys.indexes", rows)])):
            out = json.loads(res.list_mssql_indexes.invoke({"config": CONFIG}))
        assert out["indexes"][0]["is_unused"] is False

    def test_list_schemas(self):
        rows = [{"schema_name": "sales", "owner": "dbo", "table_count": 3}]
        with patch.object(res, "execute_readonly_query", _dispatch([("sys.schemas", rows)])):
            out = json.loads(res.list_mssql_schemas.invoke({"config": CONFIG}))
        assert out["total_schemas"] == 1
        assert out["schemas"][0]["schema_name"] == "sales"

    def test_get_table_structure(self):
        cols = [{"column_name": "id", "data_type": "int", "is_nullable": 0}]
        cons = [{"constraint_name": "pk", "constraint_type": "PRIMARY KEY", "column_name": "id"}]
        with patch.object(res, "execute_readonly_query", _dispatch([("sys.columns c", cols), ("key_constraints", cons)])):
            out = json.loads(res.get_table_structure.invoke({"table": "users", "config": CONFIG}))
        assert out["table"] == "users"
        assert out["columns"][0]["column_name"] == "id"
        assert out["constraints"][0]["constraint_type"] == "PRIMARY KEY"

    def test_list_logins_formats_dates(self):
        rows = [{"login_name": "sa", "login_type": "SQL_LOGIN", "is_disabled": 0,
                 "default_database_name": "master", "create_date": "2020", "modify_date": "2021"}]
        with patch.object(res, "execute_readonly_query", _dispatch([("server_principals", rows)])):
            out = json.loads(res.list_mssql_logins.invoke({"config": CONFIG}))
        assert out["total_logins"] == 1
        assert out["logins"][0]["create_date"] == "2020"

    def test_get_database_config_enriches_units(self):
        rows = [{"name": "max server memory (MB)", "value": 8192, "value_in_use": 8192,
                 "minimum": 128, "maximum": 100000, "description": "d", "is_dynamic": 1, "is_advanced": 1}]
        with patch.object(res, "execute_readonly_query", _dispatch([("sys.configurations", rows)])):
            out = json.loads(res.get_database_config.invoke({"config": CONFIG}))
        s = out["settings"][0]
        assert s["unit"] == "MB"
        assert s["value_display"] == "8.00 GB"  # 8192 MB

    def test_resource_error_path(self):
        with patch.object(res, "execute_readonly_query", side_effect=RuntimeError("denied")):
            out = json.loads(res.list_mssql_databases.invoke({"config": CONFIG}))
        assert out["error"] == "denied"


# ============================ resources unit helpers ============================
class TestResourcesUnitHelpers:
    def test_extract_setting_unit(self):
        assert res._extract_setting_unit("max server memory (MB)") == "MB"
        assert res._extract_setting_unit("remote query timeout (s)") == "s"
        assert res._extract_setting_unit("recovery interval (min)") == "min"
        assert res._extract_setting_unit("fill factor (%)") == "%"
        assert res._extract_setting_unit("max worker threads") is None
        assert res._extract_setting_unit("") is None

    def test_format_setting_value(self):
        assert res._format_setting_value(None, "MB") is None
        assert res._format_setting_value(10, None) is None
        assert res._format_setting_value(1, "MB") == "1.00 MB"
        assert res._format_setting_value(30, "s") == "30s"
        assert res._format_setting_value(5, "min") == "5min"
        assert res._format_setting_value(80, "%") == "80%"
        assert res._format_setting_value(1, "unknown") is None

    def test_dynamic_is_broad_select(self):
        assert dyn._is_broad_select_without_constraints("SELECT id FROM t") is True
        assert dyn._is_broad_select_without_constraints("SELECT id FROM t WHERE id=1") is False
        assert dyn._is_broad_select_without_constraints("SELECT TOP 10 id FROM t") is False
        assert dyn._is_broad_select_without_constraints("UPDATE t SET x=1") is False


# ============================ connection ============================
class TestMssqlConnection:
    def test_normalize_instance_defaults(self):
        out = conn.normalize_mssql_instance({})
        assert out["id"] == "mssql-1"
        assert out["port"] == 1433
        assert out["database"] == "master"

    def test_normalize_instance_bad_port_falls_back(self):
        out = conn.normalize_mssql_instance({"port": "not-a-number"})
        assert out["port"] == 1433

    def test_parse_instances_from_json_string(self):
        raw = json.dumps([{"name": "A", "host": "h1"}, "skip-me", {"name": "B", "host": "h2"}])
        out = conn.parse_mssql_instances(raw)
        assert len(out) == 2
        assert out[0]["name"] == "A"
        # enumerate(start=1) 跨越被跳过的字符串项, 第二个 dict 索引为 3
        assert out[1]["id"] == "mssql-3"

    def test_parse_instances_invalid_json(self):
        assert conn.parse_mssql_instances("{bad") == []
        assert conn.parse_mssql_instances(None) == []
        assert conn.parse_mssql_instances({"not": "list"}) == []

    def test_resolve_instance_by_id_name_default(self):
        instances = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        assert conn.resolve_mssql_instance(instances, instance_id="b")["id"] == "b"
        assert conn.resolve_mssql_instance(instances, instance_name="A")["id"] == "a"
        assert conn.resolve_mssql_instance(instances, default_instance_id="b")["id"] == "b"
        # 无匹配默认 -> 首个
        assert conn.resolve_mssql_instance(instances, default_instance_id="zzz")["id"] == "a"

    def test_resolve_instance_not_found_raises(self):
        with pytest.raises(ValueError):
            conn.resolve_mssql_instance([{"id": "a"}], instance_id="x")
        with pytest.raises(ValueError):
            conn.resolve_mssql_instance([], instance_id="a")

    def test_build_config_from_instance_defaults(self):
        out = conn.build_mssql_config_from_instance({"host": "", "user": ""})
        assert out["host"] == "localhost"
        assert out["user"] == "sa"
        assert out["database"] == "master"

    def test_create_connection_builds_conn_str_driver18(self):
        captured = {}

        def fake_connect(conn_str, timeout=None):
            captured["conn_str"] = conn_str
            captured["timeout"] = timeout
            return MagicMock()

        with patch.object(conn, "get_available_driver", return_value="ODBC Driver 18 for SQL Server"), \
             patch.object(conn.pyodbc, "connect", side_effect=fake_connect):
            conn._create_mssql_connection({"host": "h", "port": 1433, "database": "d", "user": "u", "password": "p"})
        assert "SERVER=h,1433" in captured["conn_str"]
        assert "TrustServerCertificate=yes" in captured["conn_str"]
        assert captured["timeout"] == 10

    def test_get_connection_legacy_path(self):
        with patch.object(conn, "get_available_driver", return_value="SQL Server"), \
             patch.object(conn.pyodbc, "connect", return_value=MagicMock()) as m:
            conn.get_mssql_connection(config=CONFIG)
        m.assert_called_once()

    def test_get_connection_instance_selection_in_legacy_raises(self):
        with pytest.raises(ValueError):
            conn.get_mssql_connection(config=CONFIG, instance_name="X")

    def test_get_connection_multi_instance(self):
        cfg = {"configurable": {"mssql_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha", "user": "u", "password": "p", "database": "d"}])}}
        with patch.object(conn, "get_available_driver", return_value="SQL Server"), \
             patch.object(conn.pyodbc, "connect", return_value=MagicMock()) as m:
            conn.get_mssql_connection(config=cfg, instance_name="A")
        m.assert_called_once()

    def test_credential_adapter_validate(self):
        adapter = conn.MssqlCredentialAdapter()
        adapter.validate({"host": "h"})  # no raise
        with pytest.raises(conn.CredentialValidationError):
            adapter.validate({"host": ""})
        assert adapter.get_display_name({}, 0) == "MSSQL - 1"
        assert adapter.get_display_name({"name": "X"}, 0) == "X"

    def test_build_normalized_multi_mode(self):
        cfg = {"configurable": {"mssql_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}])}}
        normalized = conn.build_mssql_normalized_from_runnable(cfg)
        assert normalized["mode"] == "multi"
        assert len(normalized["items"]) == 2

    def test_build_normalized_single_via_selection(self):
        cfg = {"configurable": {"mssql_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}])}}
        normalized = conn.build_mssql_normalized_from_runnable(cfg, instance_id="b")
        assert normalized["mode"] == "single"
        assert normalized["items"][0]["name"] == "B"

    def test_test_mssql_instance_runs_select_1(self):
        fake_cursor = MagicMock()
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor
        with patch.object(conn, "_create_mssql_connection", return_value=fake_conn):
            ok = conn.test_mssql_instance({"host": "h", "user": "u", "password": "p"})
        assert ok is True
        fake_cursor.execute.assert_called_once_with("SELECT 1")
        fake_conn.close.assert_called_once()

    def test_test_mssql_instance_no_host_raises(self):
        with pytest.raises(ValueError):
            conn.test_mssql_instance({"host": ""})

    def test_instances_prompt(self):
        cfg = {"mssql_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}]),
            "mssql_default_instance_id": "b"}
        prompt = conn.get_mssql_instances_prompt(cfg)
        assert "A, B" in prompt
        assert "「B」" in prompt
        assert conn.get_mssql_instances_prompt({}) == ""

    def test_get_connection_from_item(self):
        item = {"config": {"host": "h", "port": 1433, "database": "d", "user": "u", "password": "p"}}
        with patch.object(conn, "_create_mssql_connection", return_value=MagicMock()) as m:
            conn.get_mssql_connection_from_item(item)
        m.assert_called_once()
