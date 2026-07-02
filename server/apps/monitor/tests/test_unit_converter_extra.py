"""monitor.utils.unit_converter.UnitConverter 补充规格测试。

覆盖 suggest_unit / auto_convert / format_value / get_display_unit /
get_all_units / get_units_by_system 等 test_unit_converter.py 未覆盖的方法。
纯计算逻辑，无外部依赖，直接验证真实输出。
"""

import pydantic.root_model  # noqa

import math

import pytest

from apps.monitor.utils.unit_converter import UnitConverter

pytestmark = pytest.mark.unit


class TestSuggestUnit:
    def test_字节体系大数值建议更大单位(self):
        # 5 GiB 级别的字节数，应建议 gibibytes（落入理想区间 1~1000）
        values = [5 * 1024**3]
        assert UnitConverter.suggest_unit(values, "bytes") == "gibibytes"

    def test_空值列表返回原单位(self):
        assert UnitConverter.suggest_unit([], "bytes") == "bytes"

    def test_全部为None或NaN返回原单位(self):
        assert UnitConverter.suggest_unit([None, float("nan")], "bytes") == "bytes"

    def test_独立单位不支持转换返回原单位(self):
        # watts 是独立单位 -> 体系为 None -> 原样返回
        assert UnitConverter.suggest_unit([1, 2, 3], "watts") == "watts"

    def test_max策略选用最大值参考(self):
        # 用 max 策略，3000 counts -> thousand
        result = UnitConverter.suggest_unit([1, 2, 3000], "counts", strategy="max")
        assert result == "thousand"

    def test_p95策略忽略极端值(self):
        # 大量小值 + 一个极端值，p95 应忽略极端 -> 维持 counts
        values = [5.0] * 100 + [9_000_000.0]
        assert UnitConverter.suggest_unit(values, "counts", strategy="p95") == "counts"

    def test_mean策略(self):
        # 平均值约 2000 counts -> thousand
        result = UnitConverter.suggest_unit([2000, 2000], "counts", strategy="mean")
        assert result == "thousand"

    def test_median策略默认分支(self):
        # 传入未知策略名走 else median 分支；中位数 2000 -> thousand
        result = UnitConverter.suggest_unit([1000, 2000, 3000], "counts", strategy="median")
        assert result == "thousand"


class TestAutoConvert:
    def test_自动建议并转换(self):
        values = [2 * 1024**3]  # 2 GiB in bytes
        converted, target_unit = UnitConverter.auto_convert(values, "bytes", strategy="max")
        assert target_unit == "gibibytes"
        assert converted == [2.0]

    def test_独立单位原样返回(self):
        converted, target_unit = UnitConverter.auto_convert([1, 2, 3], "watts")
        assert target_unit == "watts"
        assert converted == [1, 2, 3]


class TestFormatValue:
    def test_大于等于100精度降一位(self):
        # precision=2, abs>=100 -> effective=1; 移除尾零
        assert UnitConverter.format_value(123.456, "bytes") == "123.5 B"

    def test_十到百区间使用默认精度(self):
        assert UnitConverter.format_value(12.345, "bytes") == "12.35 B"

    def test_小于十精度加一位(self):
        # precision=2, abs<10 -> effective=3
        assert UnitConverter.format_value(1.2345, "bytes") == "1.234 B"

    def test_None返回NA(self):
        assert UnitConverter.format_value(None, "bytes") == "N/A"

    def test_NaN返回NA(self):
        assert UnitConverter.format_value(float("nan"), "bytes") == "N/A"

    def test_展示单位为空只返回数值(self):
        # counts 的 display_unit 为空字符串
        assert UnitConverter.format_value(12.0, "counts") == "12"

    def test_百分比展示符号(self):
        assert UnitConverter.format_value(50.0, "percent") == "50 %"

    def test_自定义精度(self):
        # value>=100，precision=4 -> effective=3
        assert UnitConverter.format_value(123.45678, "bytes", precision=4) == "123.457 B"


class TestGetDisplayUnit:
    def test_已知单位映射(self):
        assert UnitConverter.get_display_unit("kibibytes") == "KiB"
        assert UnitConverter.get_display_unit("percent") == "%"

    def test_未知单位原样标准化返回(self):
        assert UnitConverter.get_display_unit("unknown_unit") == "unknown_unit"


class TestGetAllUnits:
    def test_包含体系单位与独立单位(self):
        units = UnitConverter.get_all_units()
        by_id = {u["unit_id"]: u for u in units}

        # 体系单位
        assert by_id["bytes"]["system"] == "data_bytes"
        assert by_id["bytes"]["is_standalone"] is False
        assert by_id["bytes"]["display_unit"] == "B"

        # 独立单位
        assert by_id["watts"]["is_standalone"] is True
        assert by_id["watts"]["system"] is None
        assert by_id["watts"]["description"] == "独立单位，不支持转换"

    def test_单位显示名称与分类填充(self):
        units = UnitConverter.get_all_units()
        kib = next(u for u in units if u["unit_id"] == "kibibytes")
        assert kib["unit_name"] == "kibibytes (KiB)"
        assert "category" in kib


class TestGetUnitsBySystem:
    def test_指定体系过滤(self):
        units = UnitConverter.get_units_by_system("data_bytes")
        ids = {u["unit_id"] for u in units}
        assert "bytes" in ids and "gibibytes" in ids
        assert all(u["system"] == "data_bytes" for u in units)

    def test_无参数按体系分组(self):
        grouped = UnitConverter.get_units_by_system()
        assert "data_bytes" in grouped
        # 独立单位归入 standalone 分组
        assert "standalone" in grouped
        standalone_ids = {u["unit_id"] for u in grouped["standalone"]}
        assert "watts" in standalone_ids
