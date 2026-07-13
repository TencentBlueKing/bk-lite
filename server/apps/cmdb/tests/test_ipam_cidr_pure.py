"""IPAM CIDR/利用率纯逻辑测试。规格见 docs/superpowers/specs/2026-06-23-cmdb-ipam-p1-design.md §3/§4。"""
import pytest
from apps.cmdb.utils.ipam_cidr import (
    parse_subnet, subnets_overlap, subnet_capacity, ip_in_subnet, compute_utilization,
)
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit


class TestParseSubnet:
    def test_掩码点分十进制(self):
        net = parse_subnet("10.0.1.0", "255.255.255.0")
        assert str(net) == "10.0.1.0/24"

    def test_掩码前缀位数(self):
        net = parse_subnet("10.0.1.0", "24")
        assert str(net) == "10.0.1.0/24"

    def test_主机位非零也接受(self):
        assert str(parse_subnet("10.0.1.5", "24")) == "10.0.1.0/24"

    def test_非法地址抛错(self):
        with pytest.raises(BaseAppException):
            parse_subnet("not-an-ip", "24")


class TestOverlap:
    def test_完全相同重叠(self):
        assert subnets_overlap(parse_subnet("10.0.1.0", "24"), parse_subnet("10.0.1.0", "24")) is True

    def test_包含重叠(self):
        assert subnets_overlap(parse_subnet("10.0.0.0", "16"), parse_subnet("10.0.1.0", "24")) is True

    def test_部分交叉重叠(self):
        assert subnets_overlap(parse_subnet("10.0.1.0", "24"), parse_subnet("10.0.1.128", "25")) is True

    def test_不相交不重叠(self):
        assert subnets_overlap(parse_subnet("10.0.1.0", "24"), parse_subnet("10.0.2.0", "24")) is False


class TestCapacity:
    def test_24默认扣网络号广播(self):
        assert subnet_capacity(parse_subnet("10.0.1.0", "24")) == 254

    def test_31点对点不扣(self):
        assert subnet_capacity(parse_subnet("10.0.1.0", "31")) == 2


class TestMembership:
    def test_在网段内(self):
        assert ip_in_subnet("10.0.1.88", parse_subnet("10.0.1.0", "24")) is True

    def test_不在网段内(self):
        assert ip_in_subnet("10.0.2.1", parse_subnet("10.0.1.0", "24")) is False


class TestUtilization:
    def test_常规(self):
        assert compute_utilization(254, 100) == {"size": 254, "used": 100, "available": 154, "ratio": round(100/254, 4)}

    def test_容量为零不除零(self):
        assert compute_utilization(0, 0)["ratio"] == 0
