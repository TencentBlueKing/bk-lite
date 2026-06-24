"""选子网发现：范围推导 + 下发 payload 组装（单子网）+ 回调回写。规格 §13.1/§13.2/§13.4。"""
import pytest
from unittest.mock import patch
from apps.cmdb.services.ipam_discovery import build_scan_payload

pytestmark = pytest.mark.unit

SUBNETS = {
    1: {"_id": 1, "subnet_address": "10.0.1.0", "subnet_mask": "24", "gateway": "10.0.1.1"},
    2: {"_id": 2, "subnet_address": "192.168.0.0", "subnet_mask": "30", "gateway": ""},
}


class TestBuildScanPayload:
    def test_payload单子网推导目标并排除网关(self):
        with patch("apps.cmdb.services.ipam_discovery._load_subnets_by_ids", return_value=[SUBNETS[1]]):
            payload = build_scan_payload(subnet_id=1, scan_method="icmp", ports=None)
        assert payload["model_id"] == "ip"
        assert payload["scan_method"] == "icmp"
        assert payload["subnet_id"] == 1
        assert len(payload["targets"]) == 253  # /24 去掉网络/广播/网关
        assert "10.0.1.1" not in payload["targets"]
        assert "10.0.1.0" not in payload["targets"]
        assert payload["callback_subject"] == "receive_ip_discovery_result"

    def test_subnet_id存在于payload中(self):
        with patch("apps.cmdb.services.ipam_discovery._load_subnets_by_ids", return_value=[SUBNETS[2]]):
            payload = build_scan_payload(subnet_id=2, scan_method="icmp", ports=None)
        assert "subnet_id" in payload
        assert payload["subnet_id"] == 2
        assert len(payload["targets"]) == 2  # /30 有2个主机地址

    def test_tcp默认端口(self):
        with patch("apps.cmdb.services.ipam_discovery._load_subnets_by_ids", return_value=[SUBNETS[2]]):
            payload = build_scan_payload(subnet_id=2, scan_method="tcp", ports=None)
        assert payload["ports"] == [22, 80, 443, 3389]


class TestApplyDiscoveryResult:
    def test_在线入账_未探到的自动发现置离线_手工不动(self, monkeypatch):
        from apps.cmdb.services import ipam_discovery
        monkeypatch.setattr(ipam_discovery, "_load_subnet_ips", lambda sid: [
            {"_id": 11, "ip_addr": "10.0.1.10", "auto_collect": True, "subnet_id": "1"},
            {"_id": 12, "ip_addr": "10.0.1.20", "auto_collect": True, "subnet_id": "1"},
            {"_id": 13, "ip_addr": "10.0.1.30", "auto_collect": False, "subnet_id": "1"},
        ])
        ups, offs = [], []
        monkeypatch.setattr(ipam_discovery, "_upsert_alive_ip", lambda **kw: ups.append(kw))
        monkeypatch.setattr(ipam_discovery, "_mark_offline", lambda ip_id: offs.append(ip_id))
        monkeypatch.setattr(ipam_discovery, "_writeback_subnet_utilization", lambda sids: None)

        result = ipam_discovery.apply_discovery_result(
            subnet_id=1,
            alive=[{"ip": "10.0.1.10", "mac": "AA:BB:CC:DD:EE:FF"}, {"ip": "10.0.1.40", "mac": ""}],
        )
        assert {u["ip_addr"] for u in ups} == {"10.0.1.10", "10.0.1.40"}
        assert offs == [12]
        assert result["offline"] == 1
        assert 13 not in offs
