"""monitor.utils.unit_converter.UnitConverter 生产规格测试。

规格：同体系单位间换算（base**index 倍数；时间体系用 multipliers 累乘）；
跨体系不可转换则原样返回；is_convertible 判断同体系。
指标展示的换算正确性直接影响监控读数，必须准确。
"""

import math

import pytest

from apps.monitor.utils.unit_converter import UnitConverter

pytestmark = pytest.mark.unit


class TestConvertValues:
    def test_字节体系1024进制(self):
        # bytes -> kibibytes: 2048B = 2KiB
        assert UnitConverter.convert_values([2048], "bytes", "kibibytes") == [2.0]

    def test_计数体系1000进制(self):
        assert UnitConverter.convert_values([5000], "counts", "thousand") == [5.0]

    def test_时间体系非固定进制(self):
        # 120s = 2m
        assert UnitConverter.convert_values([120], "s", "m") == [2.0]
        # 3600s = 1h
        assert UnitConverter.convert_values([3600], "s", "h") == [1.0]

    def test_相同单位原样返回(self):
        assert UnitConverter.convert_values([1, 2, 3], "bytes", "bytes") == [1, 2, 3]

    def test_跨体系不转换原样返回(self):
        # bytes 与 s 不同体系 -> 返回原值
        assert UnitConverter.convert_values([100], "bytes", "s") == [100]

    def test_空列表(self):
        assert UnitConverter.convert_values([], "bytes", "kibibytes") == []

    def test_none与nan保留(self):
        out = UnitConverter.convert_values([None, float("nan"), 1024], "bytes", "kibibytes")
        assert out[0] is None
        assert math.isnan(out[1])
        assert out[2] == 1.0


class TestIsConvertible:
    def test_同体系可转换(self):
        assert UnitConverter.is_convertible("bytes", "gibibytes") is True
        assert UnitConverter.is_convertible("s", "h") is True

    def test_跨体系不可转换(self):
        assert UnitConverter.is_convertible("bytes", "s") is False
        assert UnitConverter.is_convertible("percent", "counts") is False

    def test_相同单位可转换(self):
        assert UnitConverter.is_convertible("bytes", "bytes") is True
