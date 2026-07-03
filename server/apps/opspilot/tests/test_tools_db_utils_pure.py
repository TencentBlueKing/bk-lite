"""MySQL 工具函数单元测试。

覆盖配置上下文构造、字节/时长格式化、百分比、JSON 序列化、版本解析、
只读查询 (mock 游标)。仅 mock DB 驱动游标/连接边界,断言真实输出与契约。

(MSSQL 工具依赖 pyodbc/unixodbc 本机库,见 test_tools_mssql_utils_pure.py 单独按需跳过。)
"""

from unittest.mock import MagicMock

import pytest

from apps.opspilot.metis.llm.tools.mysql import utils as my_utils


# --------------------------------------------------------------------------- #
# MySQL utils
# --------------------------------------------------------------------------- #
class TestMysqlPrepareContext:
    def test_defaults_when_no_config(self):
        out = my_utils.prepare_context(None)
        assert out == {"host": "localhost", "port": 3306, "database": "", "user": "root", "password": ""}

    def test_reads_configurable(self):
        cfg = {"configurable": {"host": "h", "port": 3307, "database": "d", "user": "u", "password": "p"}}
        out = my_utils.prepare_context(cfg)
        assert out["host"] == "h" and out["port"] == 3307 and out["database"] == "d"


class TestMysqlFormatSize:
    @pytest.mark.parametrize("val,expected", [(None, "0 B"), (0, "0.00 B"), (1023, "1023.00 B"), (1024, "1.00 KB"), (1024 ** 3, "1.00 GB")])
    def test_format(self, val, expected):
        assert my_utils.format_size(val) == expected

    def test_petabyte_boundary(self):
        assert my_utils.format_size(1024 ** 5) == "1.00 PB"


class TestMysqlFormatDuration:
    @pytest.mark.parametrize("ms,expected", [
        (None, "0ms"),
        (0.5, "500.00μs"),
        (200, "200.00ms"),
        (1500, "1.50s"),
        (90000, "1.50min"),
        (7200000, "2.00h"),
    ])
    def test_format(self, ms, expected):
        assert my_utils.format_duration(ms) == expected


class TestMysqlCalculatePercentage:
    def test_normal(self):
        assert my_utils.calculate_percentage(25, 200) == 12.5

    def test_zero_total(self):
        assert my_utils.calculate_percentage(5, 0) == 0.0

    def test_rounding(self):
        assert my_utils.calculate_percentage(1, 3) == 33.33


class TestMysqlSafeJsonDumps:
    def test_datetime_isoformat(self):
        import datetime

        out = my_utils.safe_json_dumps({"t": datetime.datetime(2024, 1, 2, 3, 4, 5)})
        assert "2024-01-02T03:04:05" in out

    def test_non_serializable_str_fallback(self):
        class C:
            def __str__(self):
                return "obj"

        assert "obj" in my_utils.safe_json_dumps({"x": C()})


class TestMysqlExecuteReadonlyQuery:
    def test_sets_readonly_and_maps_rows(self):
        cursor = MagicMock()
        cursor.description = [("id",), ("name",)]
        cursor.fetchall.return_value = [(1, "a"), (2, "b")]
        conn = MagicMock()
        conn.cursor.return_value = cursor

        rows = my_utils.execute_readonly_query(conn, "SELECT id, name FROM t")

        assert rows == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        # 首次 execute 必须是只读事务声明
        first_call = cursor.execute.call_args_list[0]
        assert first_call.args[0] == "SET SESSION TRANSACTION READ ONLY"
        cursor.close.assert_called_once()

    def test_params_forwarded(self):
        cursor = MagicMock()
        cursor.description = [("c",)]
        cursor.fetchall.return_value = [(9,)]
        conn = MagicMock()
        conn.cursor.return_value = cursor

        my_utils.execute_readonly_query(conn, "SELECT c FROM t WHERE x=%s", ("v",))

        # 最后一次 execute 应携带参数
        last_call = cursor.execute.call_args_list[-1]
        assert last_call.args == ("SELECT c FROM t WHERE x=%s", ("v",))

    def test_cursor_closed_on_error(self):
        from mysql.connector import Error

        cursor = MagicMock()
        cursor.execute.side_effect = [None, Error("boom")]
        conn = MagicMock()
        conn.cursor.return_value = cursor

        with pytest.raises(Error):
            my_utils.execute_readonly_query(conn, "SELECT 1")
        cursor.close.assert_called_once()


class TestMysqlParseVersion:
    def test_parses_major(self):
        cursor = MagicMock()
        cursor.description = [("version",)]
        cursor.fetchall.return_value = [("8.0.32",)]
        conn = MagicMock()
        conn.cursor.return_value = cursor

        out = my_utils.parse_mysql_version(conn)
        assert out == {"full_version": "8.0.32", "major_version": 8}

    def test_error_returns_unknown(self):
        conn = MagicMock()
        conn.cursor.side_effect = Exception("down")
        out = my_utils.parse_mysql_version(conn)
        assert out == {"full_version": "unknown", "major_version": 0}


class TestMysqlValidateSqlSafety:
    def test_delegates_to_shared(self):
        ok, _ = my_utils.validate_sql_safety("SELECT 1")
        assert ok is True
        bad, msg = my_utils.validate_sql_safety("DELETE FROM t")
        assert bad is False and "delete" in msg
