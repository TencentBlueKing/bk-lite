"""MSSQL 工具函数单元测试。

MSSQL utils 在导入时即依赖 pyodbc(进而需要系统 unixodbc 动态库)。在缺少该库的
本机/CI 环境下整文件跳过,而不让收集报错。覆盖标识符引用护栏、格式化、单位字段
富化与 JSON 序列化。
"""

import pytest

# pyodbc 在导入 mssql.utils 时被加载;缺 unixodbc 时整文件跳过。
pytest.importorskip("pyodbc", reason="pyodbc/unixodbc 未安装,跳过 MSSQL 工具测试")

from apps.opspilot.metis.llm.tools.mssql import utils as ms_utils  # noqa: E402


class TestMssqlQuoteIdentifier:
    def test_valid_name(self):
        assert ms_utils.quote_database_identifier("mydb") == "[mydb]"

    def test_underscore_and_digits(self):
        assert ms_utils.quote_database_identifier("db_1") == "[db_1]"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            ms_utils.quote_database_identifier("")

    def test_injection_bracket_raises(self):
        with pytest.raises(ValueError):
            ms_utils.quote_database_identifier("db];DROP")

    def test_space_raises(self):
        with pytest.raises(ValueError):
            ms_utils.quote_database_identifier("my db")


class TestMssqlPrepareContext:
    def test_defaults(self):
        out = ms_utils.prepare_context(None)
        assert out == {"host": "localhost", "port": 1433, "database": "master", "user": "sa", "password": ""}

    def test_from_configurable(self):
        cfg = {"configurable": {"host": "h", "port": 1434, "database": "d", "user": "u", "password": "p"}}
        out = ms_utils.prepare_context(cfg)
        assert out["host"] == "h" and out["port"] == 1434


class TestMssqlFormatters:
    def test_format_size_none(self):
        assert ms_utils.format_size(None) == "0 B"

    def test_format_size_gb(self):
        assert ms_utils.format_size(1024 ** 3) == "1.00 GB"

    def test_format_duration_ms(self):
        assert ms_utils.format_duration(250) == "250.00ms"

    def test_calculate_percentage(self):
        assert ms_utils.calculate_percentage(50, 200) == 25.0
        assert ms_utils.calculate_percentage(1, 0) == 0.0


class TestMssqlEnrichUnitFields:
    def test_size_bytes_gets_display(self):
        out = ms_utils.enrich_unit_fields({"size_bytes": 1024})
        assert out["size_bytes"] == 1024
        assert out["size_bytes_display"] == "1.00 KB"

    def test_percent_field_formatted(self):
        out = ms_utils.enrich_unit_fields({"usage_percent": 12.345})
        assert out["usage_percent_display"] == "12.35%"

    def test_nested_list_recursion(self):
        out = ms_utils.enrich_unit_fields([{"avg_time_ms": 1500}])
        assert out[0]["avg_time_ms_display"] == "1.50s"

    def test_legacy_alias_added(self):
        out = ms_utils.enrich_unit_fields({"size_mb": 1})
        assert "size_formatted" in out

    def test_bool_not_treated_as_numeric(self):
        out = ms_utils.enrich_unit_fields({"usage_percent": True})
        assert "usage_percent_display" not in out

    def test_existing_display_not_overwritten(self):
        out = ms_utils.enrich_unit_fields({"size_bytes": 1024, "size_bytes_display": "custom"})
        assert out["size_bytes_display"] == "custom"


class TestMssqlSafeJsonDumps:
    def test_enriches_and_serializes(self):
        out = ms_utils.safe_json_dumps({"size_bytes": 1024})
        assert '"size_bytes_display": "1.00 KB"' in out
