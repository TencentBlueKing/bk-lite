"""MetricsInstanceViewSet 单位转换静态助手规格测试（纯函数）。"""

import pytest

from apps.monitor.views.metrics_instance import MetricsInstanceViewSet as V


class TestExtractValuesFromItem:
    def test_single_value(self):
        assert V._extract_values_from_item([100, "42"]) == [42.0]

    def test_range_values(self):
        assert V._extract_values_from_item([[1, "10"], [2, "20"]]) == [10.0, 20.0]

    def test_skips_none_and_invalid(self):
        assert V._extract_values_from_item([[1, None], [2, "x"], [3, "5"]]) == [5.0]

    def test_single_value_none(self):
        assert V._extract_values_from_item([100, None]) == []


class TestConvertSingleValue:
    def test_converts_in_place(self):
        item = {"value": [100, "2048"], "metric": {}}
        V._convert_single_value(item, [100, "2048"], "bytes", "kibibytes")
        assert item["value"][0] == 100
        assert float(item["value"][1]) == pytest.approx(2.0)

    def test_none_value_noop(self):
        item = {"metric": {}}
        V._convert_single_value(item, [100, None], "bytes", "kibibytes")
        assert "value" not in item


class TestConvertRangeValues:
    def test_converts_valid_points(self):
        values = [[1, "1024"], [2, None], [3, "2048"]]
        V._convert_range_values({"metric": {}}, values, "bytes", "kibibytes")
        assert float(values[0][1]) == pytest.approx(1.0)
        assert values[1][1] is None
        assert float(values[2][1]) == pytest.approx(2.0)

    def test_no_numeric_noop(self):
        values = [[1, None]]
        V._convert_range_values({"metric": {}}, values, "bytes", "kibibytes")
        assert values == [[1, None]]


class TestApplyUnitConversion:
    def test_non_success_returns_unchanged(self):
        data = {"status": "error"}
        assert V._apply_unit_conversion(data, "bytes") is data

    def test_empty_result_returns_unchanged(self):
        data = {"status": "success", "data": {"result": []}}
        assert V._apply_unit_conversion(data, "bytes") is data

    def test_range_conversion_with_explicit_target(self):
        data = {
            "status": "success",
            "data": {"result": [
                {"metric": {}, "values": [[1, "1024"], [2, "2048"]]},
            ]},
        }
        out = V._apply_unit_conversion(data, "bytes", target_unit="kibibytes")
        assert out["data"]["unit"] == "kibibytes"
        assert out["data"]["source_unit"] == "bytes"
        vals = out["data"]["result"][0]["values"]
        assert float(vals[0][1]) == pytest.approx(1.0)

    def test_single_value_conversion(self):
        data = {
            "status": "success",
            "data": {"result": [
                {"metric": {}, "value": [100, "2048"]},
            ]},
        }
        out = V._apply_unit_conversion(data, "bytes", target_unit="kibibytes")
        assert float(out["data"]["result"][0]["value"][1]) == pytest.approx(2.0)

    def test_auto_target_when_not_specified(self):
        data = {
            "status": "success",
            "data": {"result": [
                {"metric": {}, "values": [[1, "1048576"]]},
            ]},
        }
        out = V._apply_unit_conversion(data, "bytes")
        # 自动推荐目标单位并写入
        assert "unit" in out["data"]
