"""Oracle / PostgreSQL 工具函数单元测试。

覆盖配置上下文构造、字节/时长格式化、百分比、JSON 序列化、版本解析、
只读查询与只读事务声明 (mock 游标/连接)。仅 mock DB 驱动边界。
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.tools.oracle import utils as ora
from apps.opspilot.metis.llm.tools.postgres import utils as pg


# --------------------------------------------------------------------------- #
# Oracle
# --------------------------------------------------------------------------- #
class TestOraclePrepareContext:
    def test_defaults(self):
        out = ora.prepare_context(None)
        assert out == {"host": "localhost", "port": 1521, "database": "", "user": "", "password": ""}

    def test_from_configurable(self):
        out = ora.prepare_context({"configurable": {"host": "h", "port": 1522}})
        assert out["host"] == "h" and out["port"] == 1522


class TestOracleFormatters:
    @pytest.mark.parametrize("v,e", [(None, "0 B"), (0, "0.00 B"), (1024, "1.00 KB")])
    def test_format_size(self, v, e):
        assert ora.format_size(v) == e

    @pytest.mark.parametrize("ms,e", [(None, "0ms"), (200, "200.00ms"), (1500, "1.50s")])
    def test_format_duration(self, ms, e):
        assert ora.format_duration(ms) == e

    def test_percentage(self):
        assert ora.calculate_percentage(3, 4) == 75.0
        assert ora.calculate_percentage(1, 0) == 0.0

    def test_validate_sql_delegates(self):
        assert ora.validate_sql_safety("SELECT 1")[0] is True
        ok, msg = ora.validate_sql_safety("DROP TABLE t")
        assert ok is False and "drop" in msg


class TestOracleExecuteReadonlyQuery:
    def test_readonly_txn_then_maps_rows(self):
        cursor = MagicMock()
        cursor.description = [("ID",), ("NAME",)]
        cursor.fetchall.return_value = [(1, "a")]
        conn = MagicMock()
        conn.cursor.return_value = cursor

        rows = ora.execute_readonly_query(conn, "SELECT id, name FROM t")
        assert rows == [{"ID": 1, "NAME": "a"}]
        assert cursor.execute.call_args_list[0].args[0] == "SET TRANSACTION READ ONLY"
        cursor.close.assert_called_once()

    def test_error_propagated_cursor_closed(self):
        import oracledb

        cursor = MagicMock()
        cursor.execute.side_effect = [None, oracledb.Error("x")]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        with pytest.raises(oracledb.Error):
            ora.execute_readonly_query(conn, "SELECT 1")
        cursor.close.assert_called_once()


# --------------------------------------------------------------------------- #
# PostgreSQL
# --------------------------------------------------------------------------- #
class TestPgPrepareContext:
    def test_defaults(self):
        out = pg.prepare_context(None)
        assert out == {"host": "localhost", "port": 5432, "database": "postgres", "user": "postgres", "password": ""}

    def test_from_configurable(self):
        out = pg.prepare_context({"configurable": {"host": "h", "database": "mydb"}})
        assert out["host"] == "h" and out["database"] == "mydb"


class TestPgFormatters:
    @pytest.mark.parametrize("v,e", [(None, "0 B"), (1024 ** 2, "1.00 MB")])
    def test_format_size(self, v, e):
        assert pg.format_size(v) == e

    def test_format_duration_hours(self):
        assert pg.format_duration(7200000) == "2.00h"

    def test_percentage(self):
        assert pg.calculate_percentage(1, 8) == 12.5

    def test_safe_json_dumps_datetime(self):
        import datetime

        out = pg.safe_json_dumps({"d": datetime.date(2024, 5, 6)})
        assert "2024-05-06" in out


class TestPgExecuteReadonlyQuery:
    def test_begin_readonly_and_commit(self):
        cursor = MagicMock()
        # RealDictCursor rows behave like dicts
        cursor.fetchall.return_value = [{"a": 1}, {"a": 2}]
        conn = MagicMock()
        conn.cursor.return_value = cursor

        with patch.object(pg, "get_db_connection", return_value=conn):
            rows = pg.execute_readonly_query("SELECT a FROM t")

        assert rows == [{"a": 1}, {"a": 2}]
        assert cursor.execute.call_args_list[0].args[0] == "BEGIN TRANSACTION READ ONLY"
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_error_rolls_back(self):
        import psycopg2

        cursor = MagicMock()
        cursor.execute.side_effect = [None, psycopg2.Error("boom")]
        conn = MagicMock()
        conn.cursor.return_value = cursor

        with patch.object(pg, "get_db_connection", return_value=conn):
            with pytest.raises(psycopg2.Error):
                pg.execute_readonly_query("SELECT 1")
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()


class TestPgParseVersion:
    def test_parses_major(self):
        with patch.object(pg, "execute_readonly_query", return_value=[{"version": "PostgreSQL 14.5 on x86_64"}]):
            out = pg.parse_pg_version()
        assert out["version_number"] == "14.5"
        assert out["major_version"] == 14

    def test_error_returns_unknown(self):
        with patch.object(pg, "execute_readonly_query", side_effect=Exception("down")):
            out = pg.parse_pg_version()
        assert out["major_version"] == 0
        assert out["full_version"] == "unknown"
