"""opspilot-tools 切片：纯函数 / 工具辅助逻辑真实测试。

覆盖目标：
- common/sql_guard: SQL 安全护栏（黑名单+白名单纵深防御）、敏感字段检测/过滤、错误脱敏、阻塞卸载
- common/credentials: normalize_credentials / execute_with_credentials 多实例聚合
- mysql/utils: format_size / format_duration / calculate_percentage / safe_json_dumps / prepare_context
- mysql/connection: normalize_mysql_instance / parse_mysql_instances / resolve / build_config / 标准化构建
- redis/utils: ensure_json_serializable / 截断 / 响应构造 / require_confirm
- cmdb/utils: normalize_query_list / wrap_* / ensure_write_allowed / to_json_safe / 配置解析
- kubernetes/utils: format_bytes / parse_resource_quantity / 线程局部集群名
- mssql/utils: quote_database_identifier / format_size / format_duration / enrich_unit_fields
"""

import pytest

import pydantic.root_model  # noqa  预热，避免插件交互超时


# --------------------------------------------------------------------------- #
# common/sql_guard
# --------------------------------------------------------------------------- #
from apps.opspilot.metis.llm.tools.common import sql_guard


class TestSqlGuardForbiddenKeywords:
    def test_get_forbidden_keywords_merges_common_and_dialect(self):
        kws = sql_guard.get_forbidden_keywords("postgres")
        # 通用关键字
        assert "insert" in kws and "delete" in kws and "drop" in kws
        # postgres 方言特有
        assert "vacuum" in kws and "pg_terminate_backend" in kws
        # 不应包含其它方言特有
        assert "xp_" not in kws

    def test_get_forbidden_keywords_unknown_dialect_only_common(self):
        kws = sql_guard.get_forbidden_keywords("nope")
        assert "insert" in kws
        # 没有方言扩展
        assert "vacuum" not in kws and "xp_" not in kws


class TestValidateSqlSafety:
    def test_simple_select_passes(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT id, name FROM users WHERE id = 1", "mysql")
        assert ok is True
        assert msg == ""

    def test_with_cte_passes(self):
        ok, msg = sql_guard.validate_sql_safety("WITH t AS (SELECT 1 AS a) SELECT a FROM t", "postgres")
        assert ok is True

    def test_insert_blocked_by_keyword(self):
        ok, msg = sql_guard.validate_sql_safety("INSERT INTO t VALUES (1)", "mysql")
        assert ok is False
        assert "insert" in msg

    def test_word_boundary_avoids_false_positive_on_column_name(self):
        # inserted_at 含 insert 子串，但单词边界不应误判
        ok, msg = sql_guard.validate_sql_safety("SELECT inserted_at FROM t", "mysql")
        assert ok is True, msg

    def test_must_start_with_select_or_with(self):
        ok, msg = sql_guard.validate_sql_safety("EXPLAIN ANALYZE SELECT 1", "mysql")
        # analyze 不在 mysql 黑名单，但起始词不是 select/with -> 黑名单层先拦
        assert ok is False
        assert "SELECT或WITH" in msg

    def test_stacked_statements_blocked(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT 1; SELECT 2", "mysql")
        assert ok is False
        assert "多条" in msg

    def test_trailing_semicolon_allowed(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT 1;", "mysql")
        assert ok is True, msg

    def test_comment_injection_blocked(self):
        # guard 通过关键字黑名单拦截(注释里的 drop 也被禁),ok=False 且 msg 指明禁止关键字
        ok, msg = sql_guard.validate_sql_safety("SELECT 1 -- drop", "mysql")
        assert ok is False
        assert "drop" in msg.lower() or "禁止" in msg

    def test_block_comment_blocked(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT /* x */ 1", "mysql")
        assert ok is False
        assert "注释" in msg

    def test_mssql_prefix_keyword_xp_blocked(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT * FROM xp_cmdshell", "mssql")
        assert ok is False
        assert "xp_" in msg

    def test_oracle_prefix_keyword_dbms_blocked(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT dbms_random.value FROM dual", "oracle")
        assert ok is False
        assert "dbms_" in msg


class TestAssertSingleReadonlyStatement:
    def test_empty_after_strip_rejected(self):
        ok, msg = sql_guard._assert_single_readonly_statement("/* only comment */")
        assert ok is False
        assert "为空" in msg

    def test_non_readonly_start_rejected(self):
        ok, msg = sql_guard._assert_single_readonly_statement("UPDATE t SET a=1")
        assert ok is False
        assert "只读" in msg

    def test_stacked_rejected(self):
        ok, msg = sql_guard._assert_single_readonly_statement("SELECT 1; SELECT 2")
        assert ok is False
        assert "堆叠" in msg

    def test_strip_comments_removes_line_and_block(self):
        out = sql_guard._strip_sql_comments("SELECT 1 -- c\n/* b */ FROM t")
        assert "--" not in out and "/*" not in out
        assert "SELECT 1" in out and "FROM t" in out


class TestSensitiveDetection:
    def test_detect_select_star_true(self):
        assert sql_guard.detect_select_star("SELECT   *   FROM  users") is True

    def test_detect_select_star_false_for_columns(self):
        assert sql_guard.detect_select_star("SELECT id FROM users") is False

    def test_detect_sensitive_in_select_hit(self):
        kw = sql_guard.detect_sensitive_in_select("SELECT password FROM users")
        assert kw == "password"

    def test_detect_sensitive_in_select_none(self):
        assert sql_guard.detect_sensitive_in_select("SELECT id FROM users") is None

    def test_is_sensitive_column_substring(self):
        assert sql_guard.is_sensitive_column("user_password_hash") is True
        assert sql_guard.is_sensitive_column("username") is False

    def test_filter_sensitive_columns_removes_exact_match(self):
        rows = [{"id": 1, "password": "x", "name": "a"}, {"id": 2, "password": "y", "name": "b"}]
        out = sql_guard.filter_sensitive_columns(rows)
        assert out == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]

    def test_filter_sensitive_columns_no_sensitive_returns_same(self):
        rows = [{"id": 1, "name": "a"}]
        out = sql_guard.filter_sensitive_columns(rows)
        assert out == rows

    def test_filter_sensitive_columns_empty(self):
        assert sql_guard.filter_sensitive_columns([]) == []


class TestSanitizeAndRunBlocking:
    def test_sanitize_db_error_hides_details(self):
        msg = sql_guard.sanitize_db_error(Exception("host=10.0.0.1 user=root password=secret"), "查询")
        assert "10.0.0.1" not in msg
        assert "secret" not in msg
        assert "查询失败" in msg

    def test_run_blocking_executes_sync_when_no_loop(self):
        result = sql_guard.run_blocking(lambda a, b: a + b, 3, 4)
        assert result == 7

    async def test_run_blocking_offloads_in_event_loop(self):
        # asyncio_mode=auto：本测试在运行中的事件循环里执行
        import threading

        captured = {}

        def _work():
            captured["thread"] = threading.current_thread().name
            return 42

        result = sql_guard.run_blocking(_work)
        assert result == 42
        # 在独立线程池里执行，不是主事件循环线程
        assert captured["thread"] != threading.current_thread().name


# --------------------------------------------------------------------------- #
# common/credentials
# --------------------------------------------------------------------------- #
from apps.opspilot.metis.llm.tools.common import credentials as cred


class _FakeAdapter:
    flat_fields = ["host"]

    def build_from_flat_config(self, configurable):
        return {"host": configurable.get("host", "")}

    def build_from_credential_item(self, item):
        return {"host": item.get("host", "")}

    def validate(self, config):
        if not config.get("host"):
            raise cred.CredentialValidationError("host required")

    def get_display_name(self, source, index):
        return source.get("name") or f"Item - {index + 1}"


class TestNormalizeCredentials:
    def test_conflict_raises(self):
        with pytest.raises(cred.CredentialConflictError):
            cred.normalize_credentials({"credentials": [{"host": "h"}], "host": "x"}, _FakeAdapter())

    def test_empty_list_raises(self):
        with pytest.raises(cred.CredentialValidationError):
            cred.normalize_credentials({"credentials": []}, _FakeAdapter())

    def test_non_dict_item_raises(self):
        with pytest.raises(cred.CredentialValidationError):
            cred.normalize_credentials({"credentials": ["bad"]}, _FakeAdapter())

    def test_single_credential_mode(self):
        out = cred.normalize_credentials({"credentials": [{"host": "h1", "name": "A"}]}, _FakeAdapter())
        assert out["mode"] == "single"
        assert out["legacy_single"] is False
        assert out["items"][0]["name"] == "A"
        assert out["items"][0]["config"] == {"host": "h1"}

    def test_multi_credential_mode(self):
        out = cred.normalize_credentials(
            {"credentials": [{"host": "h1"}, {"host": "h2"}]}, _FakeAdapter()
        )
        assert out["mode"] == "multi"
        assert len(out["items"]) == 2

    def test_legacy_flat_mode(self):
        out = cred.normalize_credentials({"host": "legacy"}, _FakeAdapter())
        assert out["mode"] == "single"
        assert out["legacy_single"] is True
        assert out["items"][0]["config"] == {"host": "legacy"}

    def test_legacy_validation_failure_propagates(self):
        with pytest.raises(cred.CredentialValidationError):
            cred.normalize_credentials({}, _FakeAdapter())


class TestExecuteWithCredentials:
    def test_single_unwrap_returns_raw(self):
        normalized = cred.normalize_credentials({"host": "h"}, _FakeAdapter())
        out = cred.execute_with_credentials(normalized, lambda item: {"got": item["config"]["host"]})
        assert out == {"got": "h"}

    def test_multi_aggregates_success_and_failure(self):
        normalized = cred.normalize_credentials(
            {"credentials": [{"host": "ok", "name": "A"}, {"host": "boom", "name": "B"}]},
            _FakeAdapter(),
        )

        def _exec(item):
            if item["config"]["host"] == "boom":
                raise RuntimeError("kapow")
            return {"v": 1}

        out = cred.execute_with_credentials(normalized, _exec)
        assert out["mode"] == "multi"
        assert out["total"] == 2
        assert out["succeeded"] == 1
        assert out["failed"] == 1
        results = {r["target"]: r for r in out["results"]}
        assert results["A"]["ok"] is True and results["A"]["data"] == {"v": 1}
        assert results["B"]["ok"] is False and "kapow" in results["B"]["error"]

    def test_single_no_unwrap_aggregates(self):
        normalized = cred.normalize_credentials({"host": "h"}, _FakeAdapter())
        out = cred.execute_with_credentials(normalized, lambda item: 99, unwrap_single=False)
        assert out["mode"] == "multi"
        assert out["total"] == 1
        assert out["results"][0]["data"] == 99


# --------------------------------------------------------------------------- #
# mysql/utils
# --------------------------------------------------------------------------- #
from apps.opspilot.metis.llm.tools.mysql import utils as my_utils


class TestMysqlUtils:
    def test_prepare_context_defaults(self):
        cfg = my_utils.prepare_context(None)
        assert cfg == {"host": "localhost", "port": 3306, "database": "", "user": "root", "password": ""}

    def test_prepare_context_reads_configurable(self):
        cfg = my_utils.prepare_context({"configurable": {"host": "db", "port": 3307, "user": "u", "password": "p", "database": "d"}})
        assert cfg["host"] == "db" and cfg["port"] == 3307 and cfg["database"] == "d"

    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, "0 B"),
            (512, "512.00 B"),
            (1024, "1.00 KB"),
            (1024 ** 2, "1.00 MB"),
            (1536 * 1024 ** 2, "1.50 GB"),
        ],
    )
    def test_format_size(self, value, expected):
        assert my_utils.format_size(value) == expected

    @pytest.mark.parametrize(
        "ms,expected",
        [
            (None, "0ms"),
            (0.5, "500.00μs"),
            (200, "200.00ms"),
            (1500, "1.50s"),
            (90000, "1.50min"),
            (7200000, "2.00h"),
        ],
    )
    def test_format_duration(self, ms, expected):
        assert my_utils.format_duration(ms) == expected

    def test_calculate_percentage(self):
        assert my_utils.calculate_percentage(1, 4) == 25.0
        assert my_utils.calculate_percentage(1, 0) == 0.0

    def test_safe_json_dumps_handles_datetime(self):
        from datetime import datetime

        out = my_utils.safe_json_dumps({"t": datetime(2026, 6, 23, 1, 2, 3), "中": "文"})
        assert "2026-06-23T01:02:03" in out
        assert "中" in out  # ensure_ascii=False

    def test_validate_sql_safety_delegates(self):
        ok, _ = my_utils.validate_sql_safety("SELECT 1")
        assert ok is True
        ok2, msg2 = my_utils.validate_sql_safety("DELETE FROM t")
        assert ok2 is False and "delete" in msg2

    def test_parse_mysql_version_success(self, mocker):
        mocker.patch.object(
            my_utils, "execute_readonly_query", return_value=[{"version": "8.0.32-log"}]
        )
        out = my_utils.parse_mysql_version(object())
        assert out == {"full_version": "8.0.32-log", "major_version": 8}

    def test_parse_mysql_version_failure_returns_unknown(self, mocker):
        mocker.patch.object(my_utils, "execute_readonly_query", side_effect=RuntimeError("boom"))
        out = my_utils.parse_mysql_version(object())
        assert out == {"full_version": "unknown", "major_version": 0}


class TestExecuteReadonlyQuery:
    def test_execute_readonly_query_maps_rows_to_dicts(self, mocker):
        cursor = mocker.MagicMock()
        cursor.description = [("id",), ("name",)]
        cursor.fetchall.return_value = [(1, "a"), (2, "b")]
        conn = mocker.MagicMock()
        conn.cursor.return_value = cursor

        out = my_utils.execute_readonly_query(conn, "SELECT id, name FROM t")
        assert out == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        # 强制只读事务
        cursor.execute.assert_any_call("SET SESSION TRANSACTION READ ONLY")
        cursor.close.assert_called_once()

    def test_execute_readonly_query_with_params(self, mocker):
        cursor = mocker.MagicMock()
        cursor.description = [("c",)]
        cursor.fetchall.return_value = [(7,)]
        conn = mocker.MagicMock()
        conn.cursor.return_value = cursor

        out = my_utils.execute_readonly_query(conn, "SELECT c FROM t WHERE x=%s", (3,))
        assert out == [{"c": 7}]
        cursor.execute.assert_any_call("SELECT c FROM t WHERE x=%s", (3,))

    def test_execute_readonly_query_reraises_and_closes_cursor(self, mocker):
        from mysql.connector import Error as MyError

        cursor = mocker.MagicMock()
        cursor.execute.side_effect = [None, MyError("query failed")]  # 第二次 execute 抛错
        conn = mocker.MagicMock()
        conn.cursor.return_value = cursor

        with pytest.raises(MyError):
            my_utils.execute_readonly_query(conn, "SELECT 1")
        cursor.close.assert_called_once()


# --------------------------------------------------------------------------- #
# mysql/connection (pure)
# --------------------------------------------------------------------------- #
from apps.opspilot.metis.llm.tools.mysql import connection as my_conn


class TestMysqlConnectionPure:
    def test_normalize_instance_fills_defaults(self):
        out = my_conn.normalize_mysql_instance({})
        assert out["id"] == "mysql-1" and out["name"] == "MySQL - 1"
        assert out["port"] == 3306 and out["database"] == "mysql"
        assert out["charset"] == "utf8mb4" and out["collation"] == "utf8mb4_unicode_ci"
        assert out["ssl"] is False

    def test_normalize_instance_coerces_port_and_ssl(self):
        out = my_conn.normalize_mysql_instance({"port": "5000", "ssl": "true", "host": "h"})
        assert out["port"] == 5000 and out["ssl"] is True and out["host"] == "h"

    def test_normalize_instance_bad_port_uses_default(self):
        out = my_conn.normalize_mysql_instance({"port": "abc"})
        assert out["port"] == 3306

    def test_parse_instances_from_json_string(self):
        out = my_conn.parse_mysql_instances('[{"host": "h1"}, {"host": "h2"}]')
        assert len(out) == 2
        assert out[0]["id"] == "mysql-1" and out[1]["id"] == "mysql-2"

    def test_parse_instances_invalid_json_returns_empty(self):
        assert my_conn.parse_mysql_instances("not json") == []

    def test_parse_instances_skips_non_dict(self):
        out = my_conn.parse_mysql_instances([{"host": "h"}, "bad", 123])
        assert len(out) == 1

    def test_parse_instances_empty(self):
        assert my_conn.parse_mysql_instances(None) == []
        assert my_conn.parse_mysql_instances("{}") == []  # dict 非 list

    def test_resolve_by_id(self):
        instances = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        assert my_conn.resolve_mysql_instance(instances, instance_id="b")["name"] == "B"

    def test_resolve_by_id_not_found_raises(self):
        with pytest.raises(ValueError, match="not found"):
            my_conn.resolve_mysql_instance([{"id": "a"}], instance_id="z")

    def test_resolve_by_name(self):
        instances = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        assert my_conn.resolve_mysql_instance(instances, instance_name="A")["id"] == "a"

    def test_resolve_by_default_id(self):
        instances = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        assert my_conn.resolve_mysql_instance(instances, default_instance_id="b")["id"] == "b"

    def test_resolve_falls_back_to_first(self):
        instances = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        assert my_conn.resolve_mysql_instance(instances)["id"] == "a"

    def test_resolve_empty_raises(self):
        with pytest.raises(ValueError, match="No MySQL"):
            my_conn.resolve_mysql_instance([])

    def test_build_config_from_instance_basic(self):
        params = my_conn.build_mysql_config_from_instance({"host": "h", "user": "u", "password": "p"})
        assert params["host"] == "h" and params["user"] == "u"
        assert params["charset"] == "utf8mb4"
        assert "ssl_ca" not in params  # ssl 关闭时不应添加

    def test_build_config_from_instance_with_ssl(self):
        params = my_conn.build_mysql_config_from_instance(
            {"host": "h", "ssl": True, "ssl_ca": "/ca.pem", "ssl_cert": "/c.pem"}
        )
        assert params["ssl_ca"] == "/ca.pem" and params["ssl_cert"] == "/c.pem"

    def test_build_normalized_from_runnable_legacy_flat(self):
        out = my_conn.build_mysql_normalized_from_runnable({"configurable": {"host": "legacy"}})
        assert out["mode"] == "single" and out["legacy_single"] is True
        assert out["items"][0]["config"]["host"] == "legacy"

    def test_build_normalized_from_runnable_multi_instances(self):
        cfg = {"configurable": {"mysql_instances": [{"host": "h1", "name": "A"}, {"host": "h2", "name": "B"}]}}
        out = my_conn.build_mysql_normalized_from_runnable(cfg)
        assert out["mode"] == "multi" and len(out["items"]) == 2

    def test_build_normalized_from_runnable_specific_instance(self):
        cfg = {"configurable": {"mysql_instances": [{"id": "x", "host": "h1", "name": "A"}, {"id": "y", "host": "h2", "name": "B"}]}}
        out = my_conn.build_mysql_normalized_from_runnable(cfg, instance_id="y")
        assert out["mode"] == "single"
        assert out["items"][0]["config"]["host"] == "h2"

    def test_get_instances_prompt_describes_default(self):
        cfg = {"mysql_instances": [{"id": "a", "name": "Alpha"}, {"id": "b", "name": "Beta"}], "mysql_default_instance_id": "b"}
        prompt = my_conn.get_mysql_instances_prompt(cfg)
        assert "Alpha" in prompt and "Beta" in prompt
        assert "Beta" in prompt and "默认实例" in prompt

    def test_get_instances_prompt_empty(self):
        assert my_conn.get_mysql_instances_prompt({}) == ""

    def test_get_connection_from_item_calls_connect(self, mocker):
        created = mocker.patch.object(my_conn, "connect", return_value="CONN")
        item = {"config": {"host": "h", "user": "u"}}
        out = my_conn.get_mysql_connection_from_item(item)
        assert out == "CONN"
        # autocommit/timeout/sql_mode 被注入
        kwargs = created.call_args.kwargs
        assert kwargs["autocommit"] is True
        assert kwargs["connect_timeout"] == 10
        assert kwargs["sql_mode"] == "TRADITIONAL"
        assert kwargs["host"] == "h"


# --------------------------------------------------------------------------- #
# redis/utils
# --------------------------------------------------------------------------- #
from apps.opspilot.metis.llm.tools.redis import utils as r_utils


class TestRedisUtils:
    def test_ensure_json_serializable_primitives(self):
        assert r_utils.ensure_json_serializable(1) == 1
        assert r_utils.ensure_json_serializable(None) is None
        assert r_utils.ensure_json_serializable(True) is True

    def test_ensure_json_serializable_bytes_utf8(self):
        assert r_utils.ensure_json_serializable("héllo".encode("utf-8")) == "héllo"

    def test_ensure_json_serializable_bytes_non_utf8_hex(self):
        assert r_utils.ensure_json_serializable(b"\xff\xfe") == "fffe"

    def test_ensure_json_serializable_nested(self):
        out = r_utils.ensure_json_serializable({"k": [b"x", {1, 2}]})
        assert out["k"][0] == "x"
        assert sorted(out["k"][1]) == [1, 2]

    def test_ensure_json_serializable_dict_keys_stringified(self):
        out = r_utils.ensure_json_serializable({1: "a"})
        assert out == {"1": "a"}

    def test_ensure_json_serializable_fallback_str(self):
        class Weird:
            def __str__(self):
                return "weird"

        assert r_utils.ensure_json_serializable(Weird()) == "weird"

    def test_safe_json_dumps(self):
        out = r_utils.safe_json_dumps({"x": b"y"})
        assert out == '{"x": "y"}'

    def test_build_success_response_with_extra(self):
        out = r_utils.build_success_response([1, 2], count=2)
        assert out == {"success": True, "data": [1, 2], "count": 2}

    def test_build_error_response(self):
        out = r_utils.build_error_response(ValueError("oops"), error_type="custom")
        assert out == {"success": False, "error": "oops", "error_type": "custom"}

    def test_truncate_sequence(self):
        out = r_utils.truncate_sequence(list(range(150)), max_items=100)
        assert out["truncated"] is True
        assert out["returned_count"] == 100
        assert out["total_count"] == 150
        assert out["items"][0] == 0 and out["items"][-1] == 99

    def test_truncate_sequence_under_limit(self):
        out = r_utils.truncate_sequence([1, 2], max_items=100)
        assert out["truncated"] is False and out["returned_count"] == 2

    def test_truncate_mapping(self):
        data = {str(i): i for i in range(5)}
        out = r_utils.truncate_mapping(data, max_items=3)
        assert out["truncated"] is True
        assert out["returned_count"] == 3 and out["total_count"] == 5

    def test_require_confirm_ok(self):
        assert r_utils.require_confirm(True, "FLUSHDB") is None

    def test_require_confirm_blocks(self):
        out = r_utils.require_confirm(False, "FLUSHDB")
        assert out["success"] is False
        assert out["error_type"] == "confirmation_required"
        assert "FLUSHDB" in out["error"]


# --------------------------------------------------------------------------- #
# cmdb/utils (pure subset)
# --------------------------------------------------------------------------- #
from apps.opspilot.metis.llm.tools.cmdb import utils as cmdb_utils


class TestCmdbUtilsPure:
    def test_get_configurable_dict(self):
        assert cmdb_utils._get_configurable({"configurable": {"a": 1}}) == {"a": 1}

    def test_get_configurable_none(self):
        assert cmdb_utils._get_configurable(None) == {}

    def test_get_configurable_object(self):
        class C:
            configurable = {"x": 9}

        assert cmdb_utils._get_configurable(C()) == {"x": 9}

    def test_get_user_group_ids_from_dicts(self):
        class U:
            group_list = [{"id": "1"}, {"id": 2}]

        assert cmdb_utils._get_user_group_ids(U()) == [1, 2]

    def test_get_user_group_ids_from_scalars(self):
        class U:
            group_list = ["3", 4]

        assert cmdb_utils._get_user_group_ids(U()) == [3, 4]

    def test_get_user_group_ids_empty(self):
        class U:
            group_list = []

        assert cmdb_utils._get_user_group_ids(U()) == []

    def test_get_user_teams_no_team(self):
        assert cmdb_utils._get_user_teams(0, False, [1]) == []

    def test_get_user_teams_no_group_ids(self):
        assert cmdb_utils._get_user_teams(1, False, []) == []

    def test_get_user_teams_membership(self):
        assert cmdb_utils._get_user_teams(5, False, [5, 6]) == [5]
        assert cmdb_utils._get_user_teams(9, False, [5, 6]) == []

    def test_get_user_teams_include_children_delegates(self, mocker):
        gm = mocker.patch.object(
            cmdb_utils.GroupUtils, "get_user_authorized_child_groups", return_value=[5, 7, 8]
        )
        out = cmdb_utils._get_user_teams(5, True, [5, 6])
        assert out == [5, 7, 8]
        gm.assert_called_once_with([5, 6], 5, include_children=True)

    def test_resolve_allow_write_explicit(self):
        assert cmdb_utils._resolve_allow_write({"configurable": {"allow_write": True}}, False) is False
        assert cmdb_utils._resolve_allow_write({"configurable": {"allow_write": False}}, True) is True

    def test_resolve_allow_write_from_config(self):
        assert cmdb_utils._resolve_allow_write({"configurable": {"allow_write": True}}, None) is True
        assert cmdb_utils._resolve_allow_write({"configurable": {}}, None) is False

    def test_ensure_write_allowed_blocked_when_disabled(self):
        class U:
            is_superuser = True

        with pytest.raises(ValueError, match="disabled"):
            cmdb_utils.ensure_write_allowed(U(), False)

    def test_ensure_write_allowed_requires_superuser(self):
        class U:
            is_superuser = False

        with pytest.raises(ValueError, match="superuser"):
            cmdb_utils.ensure_write_allowed(U(), True)

    def test_ensure_write_allowed_ok(self):
        class U:
            is_superuser = True

        assert cmdb_utils.ensure_write_allowed(U(), True) is None

    def test_wrap_success_and_error(self):
        assert cmdb_utils.wrap_success([1]) == {"success": True, "data": [1]}
        assert cmdb_utils.wrap_error("nope") == {"success": False, "error": "nope"}

    def test_to_json_safe_unicode(self):
        assert cmdb_utils.to_json_safe({"中": 1}) == '{"中": 1}'

    def test_normalize_query_list_none(self):
        assert cmdb_utils.normalize_query_list(None) == []

    def test_normalize_query_list_non_list(self):
        assert cmdb_utils.normalize_query_list(42) == []

    def test_normalize_query_list_single_dict_wrapped(self):
        out = cmdb_utils.normalize_query_list({"field": "f", "type": "str=", "value": "v"})
        assert out == [{"field": "f", "type": "str=", "value": "v"}]

    def test_normalize_query_list_time_condition(self):
        out = cmdb_utils.normalize_query_list([{"field": "t", "type": "time", "start": "a", "end": "b"}])
        assert out == [{"field": "t", "type": "time", "start": "a", "end": "b"}]

    def test_normalize_query_list_time_missing_bounds_dropped(self):
        out = cmdb_utils.normalize_query_list([{"field": "t", "type": "time", "start": "a"}])
        assert out == []

    def test_normalize_query_list_drops_empty_values(self):
        items = [
            {"field": "a", "type": "str=", "value": ""},
            {"field": "b", "type": "str=", "value": []},
            {"field": "c", "type": "str=", "value": None},
            {"field": "d", "type": "str="},  # missing value
            {"field": "", "type": "str=", "value": "x"},  # missing field
            {"type": "str=", "value": "x"},  # missing field key
        ]
        assert cmdb_utils.normalize_query_list(items) == []

    def test_normalize_query_list_nested_lists_flattened(self):
        items = [[{"field": "a", "type": "str=", "value": "1"}], {"field": "b", "type": "str=", "value": "2"}]
        out = cmdb_utils.normalize_query_list(items)
        assert {"field": "a", "type": "str=", "value": "1"} in out
        assert {"field": "b", "type": "str=", "value": "2"} in out


# --------------------------------------------------------------------------- #
# kubernetes/utils (pure)
# --------------------------------------------------------------------------- #
from apps.opspilot.metis.llm.tools.kubernetes import utils as k8s_utils


class TestK8sUtilsPure:
    @pytest.mark.parametrize(
        "size,expected",
        [
            (512, "512 B"),
            (2048, "2.0 KiB"),
            (5 * 1024 ** 2, "5.0 MiB"),
            (int(2.5 * 1024 ** 3), "2.5 GiB"),
        ],
    )
    def test_format_bytes(self, size, expected):
        assert k8s_utils.format_bytes(size) == expected

    @pytest.mark.parametrize(
        "q,expected",
        [
            ("", 0),
            (None, 0),
            ("100m", 0.1),
            ("1Gi", float(1024 ** 3)),
            ("500Mi", float(500 * 1024 ** 2)),
            ("2K", 2000.0),
            ("3", 3.0),
            ("garbage", 0),
        ],
    )
    def test_parse_resource_quantity(self, q, expected):
        assert k8s_utils.parse_resource_quantity(q) == expected

    def test_thread_local_cluster_name(self):
        # 默认空
        k8s_utils._set_current_cluster_name("")
        assert k8s_utils.get_current_cluster_name() == ""
        k8s_utils._set_current_cluster_name("prod-cluster")
        assert k8s_utils.get_current_cluster_name() == "prod-cluster"
        k8s_utils._set_current_cluster_name("")  # 复位避免污染其它测试


# 注：mssql/* 依赖 pyodbc，本机缺 libodbc 原生库无法导入，整切片跳过 mssql。
