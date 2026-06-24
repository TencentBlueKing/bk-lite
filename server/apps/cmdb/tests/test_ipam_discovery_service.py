"""选子网发现：范围推导 + 下发 payload 组装 + 回调回写。规格 §13.1/§13.2/§13.4。"""
import pytest
from unittest.mock import patch
from apps.cmdb.services.ipam_discovery import build_scan_payload

pytestmark = pytest.mark.unit

SUBNETS = {
    1: {"_id": 1, "subnet_address": "10.0.1.0", "subnet_mask": "24", "gateway": "10.0.1.1"},
    2: {"_id": 2, "subnet_address": "192.168.0.0", "subnet_mask": "30", "gateway": ""},
}


class TestBuildScanPayload:
    def test_payload按子网推导目标并排除网关(self):
        with patch("apps.cmdb.services.ipam_discovery._load_subnets_by_ids", return_value=list(SUBNETS.values())):
            payload = build_scan_payload(subnet_ids=[1, 2], scan_method="icmp", ports=None)
        assert payload["model_id"] == "ip"
        assert payload["scan_method"] == "icmp"
        assert len(payload["targets"]) == 253 + 2
        assert "10.0.1.1" not in payload["targets"]
        assert "10.0.1.0" not in payload["targets"]

    def test_tcp默认端口(self):
        with patch("apps.cmdb.services.ipam_discovery._load_subnets_by_ids", return_value=[SUBNETS[2]]):
            payload = build_scan_payload(subnet_ids=[2], scan_method="tcp", ports=None)
        assert payload["ports"] == [22, 80, 443, 3389]
