# -- coding: utf-8 --
"""子网 -> 扫描目标地址：排除网络号/广播/网关。规格 §13.1。"""
import pytest
from plugins.inputs.ip_discovery.scan_targets import derive_targets

pytestmark = pytest.mark.unit


class TestDeriveTargets:
    def test_24排除网络号广播(self):
        targets = derive_targets("10.0.1.0", "24")
        assert "10.0.1.0" not in targets
        assert "10.0.1.255" not in targets
        assert "10.0.1.1" in targets
        assert len(targets) == 254

    def test_排除网关(self):
        targets = derive_targets("10.0.1.0", "24", gateway="10.0.1.1")
        assert "10.0.1.1" not in targets
        assert len(targets) == 253

    def test_前缀位数掩码(self):
        assert len(derive_targets("192.168.0.0", "30")) == 2

    def test_非法不抛只返回空(self):
        assert derive_targets("bad", "24") == []
