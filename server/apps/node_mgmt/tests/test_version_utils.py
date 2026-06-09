"""node_mgmt.utils.version_utils.VersionUtils 纯单元测试。

规格：解析三位版本号(x.x.x，容忍 v 前缀/空格/缺位)，非法输入归零；
is_upgradeable 当 current < latest 时为 True，空值为 False。
"""

import pytest

from apps.node_mgmt.utils.version_utils import VersionUtils

pytestmark = pytest.mark.unit


class TestParseVersion:
    @pytest.mark.parametrize("raw,expected", [
        ("1.2.3", (1, 2, 3)),
        ("v1.2.3", (1, 2, 3)),
        ("  V2.0.1 ", (2, 0, 1)),
        ("1.2", (1, 2, 0)),
        ("1", (1, 0, 0)),
        ("1.2.3.4", (1, 2, 3)),   # 多余位被截断
        ("", (0, 0, 0)),
        ("abc", (0, 0, 0)),
        ("1.x.3", (0, 0, 0)),     # 非数字整体归零
    ])
    def test_parse(self, raw, expected):
        assert VersionUtils.parse_version(raw) == expected


class TestIsUpgradeable:
    def test_可升级(self):
        assert VersionUtils.is_upgradeable("1.0.0", "1.0.1") is True
        assert VersionUtils.is_upgradeable("1.2.0", "2.0.0") is True

    def test_相等或更高不可升级(self):
        assert VersionUtils.is_upgradeable("1.0.0", "1.0.0") is False
        assert VersionUtils.is_upgradeable("2.0.0", "1.9.9") is False

    @pytest.mark.parametrize("cur,latest", [("", "1.0.0"), ("1.0.0", ""), ("", "")])
    def test_空值不可升级(self, cur, latest):
        assert VersionUtils.is_upgradeable(cur, latest) is False
