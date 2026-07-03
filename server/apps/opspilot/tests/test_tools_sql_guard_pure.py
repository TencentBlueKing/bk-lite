"""共享 SQL 安全护栏 (common/sql_guard) 纯函数单元测试。

覆盖黑名单/白名单纵深防御、敏感字段检测与过滤、错误脱敏、阻塞卸载。
全部为纯逻辑,无 DB/IO 依赖。
"""

import asyncio

import pytest

from apps.opspilot.metis.llm.tools.common import sql_guard


class TestGetForbiddenKeywords:
    def test_common_keywords_always_present(self):
        kws = sql_guard.get_forbidden_keywords("mysql")
        for common in ("insert", "update", "delete", "drop", "create"):
            assert common in kws

    def test_dialect_specific_appended(self):
        pg = sql_guard.get_forbidden_keywords("postgres")
        assert "vacuum" in pg and "pg_terminate_backend" in pg
        mssql = sql_guard.get_forbidden_keywords("mssql")
        assert "xp_" in mssql and "openrowset" in mssql

    def test_unknown_dialect_returns_only_common(self):
        kws = sql_guard.get_forbidden_keywords("unknown_db")
        # unknown 方言无特有关键字,长度等于公共表
        assert set(kws) == set(sql_guard._COMMON_FORBIDDEN)


class TestValidateSqlSafety:
    def test_plain_select_is_safe(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT id, name FROM users", "mysql")
        assert ok is True
        assert msg == ""

    def test_with_cte_is_safe(self):
        ok, _ = sql_guard.validate_sql_safety("WITH t AS (SELECT 1 AS a) SELECT a FROM t", "postgres")
        assert ok is True

    def test_insert_is_blocked(self):
        ok, msg = sql_guard.validate_sql_safety("INSERT INTO users VALUES (1)", "mysql")
        assert ok is False
        assert "insert" in msg

    def test_drop_blocked(self):
        ok, msg = sql_guard.validate_sql_safety("DROP TABLE users", "mysql")
        assert ok is False
        assert "drop" in msg

    def test_word_boundary_avoids_false_positive(self):
        # inserted_at 字段名不应触发 insert 关键字
        ok, msg = sql_guard.validate_sql_safety("SELECT inserted_at FROM logs", "mysql")
        assert ok is True, msg

    def test_must_start_with_select_or_with(self):
        ok, msg = sql_guard.validate_sql_safety("SHOW TABLES", "mysql")
        assert ok is False
        assert "SELECT" in msg

    def test_stacked_query_blocked(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT 1; SELECT 2", "mysql")
        assert ok is False
        assert "多条" in msg

    def test_trailing_semicolon_allowed(self):
        ok, _ = sql_guard.validate_sql_safety("SELECT 1;", "mysql")
        assert ok is True

    def test_comment_injection_blocked(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT 1 -- comment", "mysql")
        assert ok is False
        assert "注释" in msg

    def test_block_comment_blocked(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT /* x */ 1", "mysql")
        assert ok is False
        assert "注释" in msg

    def test_postgres_prefix_keyword_dbms_blocked_in_oracle(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT dbms_random.value FROM dual", "oracle")
        assert ok is False
        assert "dbms_" in msg

    def test_mssql_sp_prefix_blocked(self):
        ok, msg = sql_guard.validate_sql_safety("SELECT sp_who FROM x", "mssql")
        assert ok is False


class TestSingleReadonlyStatement:
    def test_empty_after_strip_rejected(self):
        ok, msg = sql_guard._assert_single_readonly_statement("   ")
        assert ok is False
        assert "为空" in msg

    def test_non_select_rejected(self):
        ok, msg = sql_guard._assert_single_readonly_statement("UPDATE x SET a=1")
        assert ok is False

    def test_explain_allowed(self):
        ok, _ = sql_guard._assert_single_readonly_statement("EXPLAIN SELECT 1")
        assert ok is True

    def test_strip_comments_then_detects_stacked(self):
        ok, msg = sql_guard._assert_single_readonly_statement("SELECT 1; SELECT 2")
        assert ok is False
        assert "堆叠" in msg


class TestStripSqlComments:
    def test_line_comment_removed(self):
        assert "secret" not in sql_guard._strip_sql_comments("SELECT 1 -- secret")

    def test_block_comment_removed(self):
        out = sql_guard._strip_sql_comments("SELECT /* hidden */ 1")
        assert "hidden" not in out


class TestSensitiveDetection:
    def test_detect_select_star_true(self):
        assert sql_guard.detect_select_star("select   *   from   users") is True

    def test_detect_select_star_false(self):
        assert sql_guard.detect_select_star("SELECT id FROM users") is False

    def test_detect_sensitive_in_select_hit(self):
        kw = sql_guard.detect_sensitive_in_select("SELECT password FROM users")
        assert kw == "password"

    def test_detect_sensitive_in_select_none(self):
        assert sql_guard.detect_sensitive_in_select("SELECT id FROM users") is None

    def test_is_sensitive_column_substring(self):
        assert sql_guard.is_sensitive_column("user_password_hash") is True
        assert sql_guard.is_sensitive_column("display_name") is False

    def test_filter_sensitive_columns_removes_exact_match(self):
        rows = [{"id": 1, "password": "x", "name": "a"}]
        out = sql_guard.filter_sensitive_columns(rows)
        assert out == [{"id": 1, "name": "a"}]

    def test_filter_sensitive_columns_empty_passthrough(self):
        assert sql_guard.filter_sensitive_columns([]) == []

    def test_filter_sensitive_columns_no_sensitive_returns_same(self):
        rows = [{"id": 1, "name": "a"}]
        assert sql_guard.filter_sensitive_columns(rows) == rows


class TestSanitizeDbError:
    def test_returns_generic_message_without_details(self):
        exc = Exception("host=10.0.0.1 password=secret123")
        msg = sql_guard.sanitize_db_error(exc, context="测试查询")
        assert "10.0.0.1" not in msg
        assert "secret123" not in msg
        assert "测试查询失败" in msg


class TestRunBlocking:
    def test_sync_context_executes_directly(self):
        assert sql_guard.run_blocking(lambda x: x * 2, 21) == 42

    def test_async_context_offloads_to_thread(self):
        async def _go():
            return sql_guard.run_blocking(lambda: 7 + 1)

        assert asyncio.run(_go()) == 8
