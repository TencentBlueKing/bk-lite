"""PostgreSQL @tool 工具集单元测试 (postgres/diagnostics|dynamic|resources|connection)。

mock 边界:
- diagnostics/dynamic/resources: 模块内 execute_readonly_query(真实 DB 边界, 内部走
  psycopg2.connect),用按 SQL 关键字分派的 side_effect 返回真实形态 dict 行。
- connection: psycopg2.connect 打桩,验证 RealDictCursor 连接参数与实例解析。

断言派生指标(健康分/usage_percent/缓存命中率)、安全护栏(SELECT */敏感字段)、
LIMIT 注入改写、大小格式化、异常脱敏透出。不连真实 PostgreSQL。
"""

import json
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest

from apps.opspilot.metis.llm.tools.postgres import connection as conn  # noqa: E402
from apps.opspilot.metis.llm.tools.postgres import diagnostics as diag  # noqa: E402
from apps.opspilot.metis.llm.tools.postgres import dynamic as dyn  # noqa: E402
from apps.opspilot.metis.llm.tools.postgres import resources as res  # noqa: E402

CONFIG = {"configurable": {"host": "127.0.0.1", "port": 5432, "user": "postgres", "password": "p", "database": "appdb"}}


def _dispatch(matchers):
    def _impl(query, params=None, config=None, database=None):
        for substr, rows in matchers:
            if substr in query:
                return rows
        return []

    return _impl


# ============================ diagnostics ============================
class TestPgDiagnostics:
    def test_slow_queries_formats(self):
        rows = [{"query": "SELECT 1", "calls": 5, "total_time": 5000, "mean_time": 1000,
                 "max_time": 2000, "total_rows": 10, "rows_per_call": 2}]
        with patch.object(diag, "execute_readonly_query", _dispatch([("pg_stat_statements", rows)])):
            out = json.loads(diag.diagnose_slow_queries.invoke({"config": CONFIG}))
        assert out["total_slow_queries"] == 1
        assert out["slow_queries"][0]["total_time_formatted"] == "5.00s"
        assert out["slow_queries"][0]["mean_time_formatted"] == "1.00s"

    def test_slow_queries_extension_missing(self):
        with patch.object(diag, "execute_readonly_query", side_effect=RuntimeError("relation pg_stat_statements does not exist")):
            out = json.loads(diag.diagnose_slow_queries.invoke({"config": CONFIG}))
        assert "pg_stat_statements扩展" in out["error"]

    def test_slow_queries_other_error(self):
        with patch.object(diag, "execute_readonly_query", side_effect=RuntimeError("permission denied")):
            out = json.loads(diag.diagnose_slow_queries.invoke({"config": CONFIG}))
        assert out["error"] == "permission denied"

    def test_lock_conflicts(self):
        rows = [{"blocked_pid": 10, "blocking_pid": 11, "blocked_query": "UPDATE",
                 "blocking_query": "SELECT", "blocked_duration": "0:01:00"}]
        with patch.object(diag, "execute_readonly_query", _dispatch([("blocked_locks", rows)])):
            out = json.loads(diag.diagnose_lock_conflicts.invoke({"config": CONFIG}))
        assert out["has_conflicts"] is True
        assert out["lock_conflicts"][0]["blocked_duration"] == "0:01:00"

    def test_connection_issues_usage(self):
        matchers = [
            ("max_connections", [{"max_connections": 100}]),
            ("FILTER (WHERE state", [{"database": "appdb", "username": "u", "state": "active",
                                      "connection_count": 50, "idle_count": 0, "active_count": 50,
                                      "idle_in_transaction_count": 0}]),
            ("interval '5 minutes'", [{"pid": 5, "usename": "u", "datname": "appdb", "state": "active",
                                       "query": "SELECT", "duration": "0:06:00"}]),
        ]
        with patch.object(diag, "execute_readonly_query", _dispatch(matchers)):
            out = json.loads(diag.diagnose_connection_issues.invoke({"config": CONFIG}))
        assert out["max_connections"] == 100
        assert out["current_connections"] == 50
        assert out["usage_percent"] == 50.0
        assert out["is_near_limit"] is False
        assert out["long_running_queries"][0]["duration"] == "0:06:00"

    def test_health_check_scoring(self):
        stats = [{"max_connections": 100, "current_connections": 95, "active_queries": 5,
                  "idle_in_transaction": 12, "long_running_queries": 2, "total_backends": 95}]
        deadlocks = [{"database": "appdb", "deadlocks": 3}]
        old_tx = [{"pid": 1, "usename": "u", "datname": "appdb", "state": "active",
                   "transaction_age": "0:10:00", "query": "X"}]
        with patch.object(diag, "execute_readonly_query", _dispatch([
            ("total_backends", stats),
            ("WHERE deadlocks", deadlocks),
            ("xact_start", old_tx),
        ])):
            out = json.loads(diag.check_database_health.invoke({"config": CONFIG}))
        # 95%(-20) + idle_in_tx>10(-15) + long_running(-15) + deadlocks(-10) = 40
        assert out["health_score"] == 40
        assert out["health_status"] == "critical"
        assert out["old_transactions"][0]["transaction_age"] == "0:10:00"

    def test_replication_lag_none(self):
        with patch.object(diag, "execute_readonly_query", _dispatch([("pg_stat_replication", [])])):
            out = json.loads(diag.check_replication_lag.invoke({"config": CONFIG}))
        assert out["has_replication"] is False

    def test_replication_lag_with_replica(self):
        rows = [{"client_addr": "10.0.0.2", "state": "streaming", "sync_state": "async",
                 "write_lag": None, "flush_lag": "0:00:01", "replay_lag": None}]
        with patch.object(diag, "execute_readonly_query", _dispatch([("pg_stat_replication", rows)])):
            out = json.loads(diag.check_replication_lag.invoke({"config": CONFIG}))
        assert out["has_replication"] is True
        assert out["replicas"][0]["write_lag"] == "0"  # None -> "0"
        assert out["replicas"][0]["flush_lag"] == "0:00:01"

    def test_autovacuum_issues(self):
        rows = [{"schemaname": "public", "table_name": "t", "live_tuples": 100, "dead_tuples": 5000,
                 "dead_tuple_percent": 98.0, "last_vacuum": None, "last_autovacuum": "2024",
                 "last_analyze": None, "last_autoanalyze": None, "time_since_vacuum": None}]
        with patch.object(diag, "execute_readonly_query", _dispatch([("pg_stat_user_tables", rows)])):
            out = json.loads(diag.diagnose_autovacuum_issues.invoke({"config": CONFIG}))
        assert out["tables_need_vacuum"] == 1
        assert out["tables"][0]["last_vacuum"] == "Never"
        assert out["tables"][0]["last_autovacuum"] == "2024"

    def test_failed_transactions(self):
        rows = [{"database": "appdb", "committed_transactions": 1000, "rolled_back_transactions": 50,
                 "rollback_percent": 4.76, "blocks_read": 10, "blocks_hit": 990,
                 "cache_hit_ratio": 99.0, "deadlocks": 0, "conflicts": 0}]
        with patch.object(diag, "execute_readonly_query", _dispatch([("pg_stat_database", rows)])):
            out = json.loads(diag.get_failed_transactions.invoke({"config": CONFIG}))
        assert out["total_databases"] == 1
        assert out["databases"][0]["cache_hit_ratio"] == 99.0


# ============================ dynamic ============================
class TestPgDynamic:
    def test_table_schema_details_not_found(self):
        with patch.object(dyn, "execute_readonly_query", _dispatch([("table_info", [])])):
            out = json.loads(dyn.get_table_schema_details.invoke({"table_name": "t", "config": CONFIG}))
        assert "不存在" in out["error"]

    def test_table_schema_details_returns_json(self):
        details = {"table_info": {"table_name": "t", "estimated_rows": 5},
                   "columns": [{"column_name": "id"}], "indexes": None, "foreign_keys": None}
        rows = [{"schema_details": details}]
        with patch.object(dyn, "execute_readonly_query", _dispatch([("schema_details", rows)])):
            out = json.loads(dyn.get_table_schema_details.invoke({"table_name": "t", "config": CONFIG}))
        assert out["table_info"]["table_name"] == "t"
        assert out["columns"][0]["column_name"] == "id"

    def test_search_tables(self):
        rows = [{"schema_name": "public", "table_name": "users", "estimated_rows": 10,
                 "table_match_type": "table_name", "matching_columns": None}]
        with patch.object(dyn, "execute_readonly_query", _dispatch([("matching_tables", rows)])):
            out = json.loads(dyn.search_tables_by_keyword.invoke({"keyword": "user", "config": CONFIG}))
        assert out["total_matches"] == 1

    def test_search_tables_no_comments_param_path(self):
        rows = []
        with patch.object(dyn, "execute_readonly_query", _dispatch([("matching_tables", rows)])):
            out = json.loads(dyn.search_tables_by_keyword.invoke(
                {"keyword": "u", "search_in_comments": False, "config": CONFIG}))
        assert out["total_matches"] == 0

    def test_execute_safe_select_rejects_star(self):
        out = json.loads(dyn.execute_safe_select.invoke({"sql": "SELECT * FROM users", "config": CONFIG}))
        assert "SELECT *" in out["error"]

    def test_execute_safe_select_rejects_sensitive(self):
        out = json.loads(dyn.execute_safe_select.invoke({"sql": "SELECT id, password FROM users", "config": CONFIG}))
        assert "敏感字段" in out["error"]

    def test_execute_safe_select_injects_limit(self):
        captured = {}

        def _impl(query, params=None, config=None, database=None):
            captured["sql"] = query
            return [{"id": 1}]

        with patch.object(dyn, "execute_readonly_query", _impl):
            out = json.loads(dyn.execute_safe_select.invoke({"sql": "SELECT id FROM users WHERE id=1", "limit": 30, "config": CONFIG}))
        assert out["success"] is True
        assert out["limit"] == 30
        assert "LIMIT 30" in captured["sql"]

    def test_execute_safe_select_caps_existing_limit(self):
        captured = {}

        def _impl(query, params=None, config=None, database=None):
            captured["sql"] = query
            return []

        with patch.object(dyn, "execute_readonly_query", _impl):
            dyn.execute_safe_select.invoke({"sql": "SELECT id FROM t LIMIT 9999", "limit": 100, "config": CONFIG})
        assert "LIMIT 100" in captured["sql"]
        assert "LIMIT 9999" not in captured["sql"]

    def test_explain_query_plan(self):
        plan = {"Plan": {"Total Cost": 12.5, "Plan Rows": 100, "Plan Width": 8}}
        rows = [{"QUERY PLAN": [plan]}]
        with patch.object(dyn, "execute_readonly_query", _dispatch([("EXPLAIN", rows)])):
            out = json.loads(dyn.explain_query_plan.invoke({"sql": "SELECT id FROM t WHERE id=1", "config": CONFIG}))
        assert out["success"] is True
        assert out["summary"]["total_cost"] == 12.5
        assert out["summary"]["estimated_rows"] == 100

    def test_explain_query_plan_analyze(self):
        plan = {"Plan": {"Total Cost": 1, "Plan Rows": 1, "Plan Width": 4,
                         "Actual Total Time": 0.5, "Actual Rows": 1},
                "Execution Time": 1.2, "Planning Time": 0.3}
        rows = [{"QUERY PLAN": [plan]}]
        with patch.object(dyn, "execute_readonly_query", _dispatch([("EXPLAIN", rows)])):
            out = json.loads(dyn.explain_query_plan.invoke({"sql": "SELECT id FROM t WHERE id=1", "analyze": True, "config": CONFIG}))
        assert out["summary"]["execution_time_ms"] == 1.2
        assert out["summary"]["actual_rows"] == 1

    def test_get_sample_data_requires_columns(self):
        out = json.loads(dyn.get_sample_data.invoke({"table_name": "users", "config": CONFIG}))
        assert "必须明确指定" in out["error"]

    def test_get_sample_data_rejects_sensitive(self):
        out = json.loads(dyn.get_sample_data.invoke({"table_name": "users", "columns": "id,api_key", "config": CONFIG}))
        assert "敏感字段" in out["error"]

    def test_get_sample_data_invalid_table(self):
        out = json.loads(dyn.get_sample_data.invoke({"table_name": "bad-name", "columns": "id", "config": CONFIG}))
        assert out["error"] == "无效的表名"

    def test_get_sample_data_success(self):
        with patch.object(dyn, "execute_readonly_query", _dispatch([("FROM public.users", [{"id": 1, "name": "a"}])])):
            out = json.loads(dyn.get_sample_data.invoke({"table_name": "users", "columns": "id,name", "config": CONFIG}))
        assert out["success"] is True
        assert out["table"] == "public.users"

    def test_execute_safe_select_batch(self):
        fake_cur = MagicMock()
        fake_cur.description = [("id",), ("name",)]
        fake_cur.fetchmany.return_value = [(1, "a")]
        cm = MagicMock()
        cm.__enter__.return_value = fake_cur
        cm.__exit__.return_value = False
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = cm
        with patch.object(dyn, "validate_sql_safety", return_value=(True, "")), \
             patch("apps.opspilot.metis.llm.tools.postgres.connection.get_postgres_connection_from_item", return_value=fake_conn):
            out = json.loads(dyn.execute_safe_select_batch.invoke(
                {"queries": ["SELECT id, name FROM users WHERE id=1"], "config": CONFIG}))
        assert out["succeeded"] == 1
        assert out["results"][0]["ok"] is True
        fake_conn.close.assert_called_once()

    def test_execute_safe_select_batch_rejects_star(self):
        with patch.object(dyn, "validate_sql_safety", return_value=(True, "")):
            out = json.loads(dyn.execute_safe_select_batch.invoke({"queries": ["SELECT * FROM t WHERE id=1"], "config": CONFIG}))
        assert out["failed"] == 1


# ============================ resources ============================
class TestPgResources:
    def test_current_database_info(self):
        rows = [{"database_name": "appdb", "username": "postgres", "pg_version": "16",
                 "current_schema": "public", "search_path": "public"}]
        with patch.object(res, "execute_readonly_query", _dispatch([("current_database()", rows)])):
            out = json.loads(res.get_current_database_info.invoke({"config": CONFIG}))
        assert out["current_database"] == "appdb"
        assert out["postgres_version"] == "16"

    def test_list_databases_formats_size(self):
        rows = [{"name": "appdb", "size_bytes": 1048576, "connections": 3, "owner": "postgres",
                 "encoding": "UTF8", "collate": "C"}]
        with patch.object(res, "execute_readonly_query", _dispatch([("pg_database", rows)])):
            out = json.loads(res.list_postgres_databases.invoke({"config": CONFIG}))
        assert out["databases"][0]["size"] == "1.00 MB"

    def test_list_tables(self):
        rows = [{"table_name": "orders", "total_size_bytes": 2097152, "table_size_bytes": 1048576,
                 "indexes_size_bytes": 1048576, "row_estimate": 100, "index_count": 2, "last_analyze": None}]
        with patch.object(res, "execute_readonly_query", _dispatch([("pg_tables", rows)])):
            out = json.loads(res.list_postgres_tables.invoke({"config": CONFIG}))
        t = out["tables"][0]
        assert t["total_size"] == "2.00 MB"
        assert t["last_analyze"] == "Never"

    def test_list_indexes_with_table_unused(self):
        rows = [{"index_name": "idx", "table_name": "t", "size_bytes": 1024, "definition": "...",
                 "index_scans": 0, "tuples_read": 0, "tuples_fetched": 0}]
        with patch.object(res, "execute_readonly_query", _dispatch([("pg_indexes", rows)])):
            out = json.loads(res.list_postgres_indexes.invoke({"table": "t", "config": CONFIG}))
        assert out["indexes"][0]["is_unused"] is True
        assert out["indexes"][0]["size"] == "1.00 KB"

    def test_list_indexes_without_table(self):
        rows = [{"index_name": "idx2", "table_name": "t2", "size_bytes": 2048, "definition": "d",
                 "index_scans": 5, "tuples_read": 1, "tuples_fetched": 1}]
        with patch.object(res, "execute_readonly_query", _dispatch([("pg_indexes", rows)])):
            out = json.loads(res.list_postgres_indexes.invoke({"config": CONFIG}))
        assert out["indexes"][0]["is_unused"] is False

    def test_list_schemas(self):
        rows = [{"schema_name": "public", "owner": "postgres", "table_count": 5}]
        with patch.object(res, "execute_readonly_query", _dispatch([("pg_namespace", rows)])):
            out = json.loads(res.list_postgres_schemas.invoke({"config": CONFIG}))
        assert out["total_schemas"] == 1

    def test_get_table_structure(self):
        cols = [{"column_name": "id", "data_type": "integer", "is_nullable": "NO"}]
        cons = [{"constraint_name": "pk", "constraint_type": "PRIMARY KEY", "column_name": "id"}]
        with patch.object(res, "execute_readonly_query", _dispatch([
            ("information_schema.columns", cols), ("table_constraints", cons)])):
            out = json.loads(res.get_table_structure.invoke({"table": "users", "config": CONFIG}))
        assert out["columns"][0]["column_name"] == "id"
        assert out["constraints"][0]["constraint_type"] == "PRIMARY KEY"

    def test_list_extensions(self):
        rows = [{"extension_name": "pg_trgm", "version": "1.6", "schema": "public", "description": "d"}]
        with patch.object(res, "execute_readonly_query", _dispatch([("pg_extension", rows)])):
            out = json.loads(res.list_postgres_extensions.invoke({"config": CONFIG}))
        assert out["total_extensions"] == 1

    def test_list_roles_formats_date(self):
        rows = [{"role_name": "postgres", "is_superuser": True, "can_create_db": True,
                 "can_create_role": True, "can_login": True, "connection_limit": -1, "valid_until": None}]
        with patch.object(res, "execute_readonly_query", _dispatch([("pg_roles", rows)])):
            out = json.loads(res.list_postgres_roles.invoke({"config": CONFIG}))
        assert out["roles"][0]["valid_until"] == "No expiration"

    def test_get_database_config(self):
        rows = [{"name": "shared_buffers", "setting": "16384", "unit": "8kB", "category": "Memory",
                 "description": "d", "source": "configuration file", "min_val": "16", "max_val": "1000"}]
        with patch.object(res, "execute_readonly_query", _dispatch([("pg_settings", rows)])):
            out = json.loads(res.get_database_config.invoke({"config": CONFIG}))
        assert out["total_settings"] == 1
        assert out["settings"][0]["name"] == "shared_buffers"

    def test_resource_error_path(self):
        with patch.object(res, "execute_readonly_query", side_effect=RuntimeError("boom")):
            out = json.loads(res.list_postgres_databases.invoke({"config": CONFIG}))
        assert out["error"] == "boom"


# ============================ connection ============================
class TestPgConnection:
    def test_normalize_instance_defaults(self):
        out = conn.normalize_postgres_instance({})
        assert out["id"] == "postgres-1"
        assert out["port"] == 5432
        assert out["database"] == "postgres"

    def test_normalize_instance_bad_port(self):
        assert conn.normalize_postgres_instance({"port": "xx"})["port"] == 5432

    def test_parse_instances_json(self):
        raw = json.dumps([{"name": "A", "host": "h1"}, {"name": "B", "host": "h2"}])
        out = conn.parse_postgres_instances(raw)
        assert len(out) == 2
        assert out[1]["id"] == "postgres-2"

    def test_parse_instances_invalid(self):
        assert conn.parse_postgres_instances("{bad") == []
        assert conn.parse_postgres_instances(None) == []
        assert conn.parse_postgres_instances("\"notlist\"") == []

    def test_resolve_instance(self):
        instances = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        assert conn.resolve_postgres_instance(instances, instance_id="b")["id"] == "b"
        assert conn.resolve_postgres_instance(instances, instance_name="A")["id"] == "a"
        assert conn.resolve_postgres_instance(instances, default_instance_id="b")["id"] == "b"
        assert conn.resolve_postgres_instance(instances)["id"] == "a"

    def test_resolve_instance_not_found(self):
        with pytest.raises(ValueError):
            conn.resolve_postgres_instance([{"id": "a"}], instance_name="X")
        with pytest.raises(ValueError):
            conn.resolve_postgres_instance([])

    def test_build_config_from_item_defaults(self):
        out = conn.build_postgres_config_from_item({"config": {"host": "", "user": ""}})
        assert out["host"] == "localhost"
        assert out["user"] == "postgres"
        assert out["database"] == "postgres"

    def test_adapter(self):
        a = conn.PostgresCredentialAdapter()
        a.validate({"host": "h"})
        with pytest.raises(conn.CredentialValidationError):
            a.validate({"host": ""})
        assert a.get_display_name({}, 1) == "PostgreSQL - 2"
        cfg = a.build_from_credential_item({"host": "h", "database": "d"})
        assert cfg["host"] == "h"
        flat = a.build_from_flat_config({"host": "fh"})
        assert flat["host"] == "fh"

    def test_build_normalized_multi(self):
        cfg = {"configurable": {"postgres_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}])}}
        n = conn.build_postgres_normalized_from_runnable(cfg)
        assert n["mode"] == "multi"
        assert len(n["items"]) == 2

    def test_build_normalized_single_select(self):
        cfg = {"configurable": {"postgres_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}])}}
        n = conn.build_postgres_normalized_from_runnable(cfg, instance_name="B")
        assert n["mode"] == "single"
        assert n["items"][0]["name"] == "B"

    def test_get_connection_from_item(self):
        item = {"config": {"host": "h", "port": 5432, "database": "d", "user": "u", "password": "p"}}
        with patch.object(conn.psycopg2, "connect", return_value=MagicMock()) as m:
            conn.get_postgres_connection_from_item(item)
        kwargs = m.call_args.kwargs
        assert kwargs["host"] == "h"
        assert kwargs["cursor_factory"] is conn.RealDictCursor
        assert kwargs["connect_timeout"] == 10

    def test_test_instance_runs_select_1(self):
        fake_cur = MagicMock()
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cur
        with patch.object(conn.psycopg2, "connect", return_value=fake_conn):
            ok = conn.test_postgres_instance({"host": "h", "user": "u", "password": "p"})
        assert ok is True
        fake_cur.execute.assert_called_once_with("SELECT 1")
        fake_conn.close.assert_called_once()

    def test_test_instance_no_host(self):
        with pytest.raises(ValueError):
            conn.test_postgres_instance({"host": ""})

    def test_instances_prompt(self):
        cfg = {"postgres_instances": json.dumps([
            {"id": "a", "name": "A", "host": "ha"}, {"id": "b", "name": "B", "host": "hb"}]),
            "postgres_default_instance_id": "b"}
        prompt = conn.get_postgres_instances_prompt(cfg)
        assert "A, B" in prompt
        assert "「B」" in prompt
        assert conn.get_postgres_instances_prompt({}) == ""
