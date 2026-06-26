# -- coding: utf-8 --
"""IP 视图数据组装。规格 §5/§7.2：返回容量、各状态计数、落库 IP 列表。"""
import pytest
from unittest.mock import patch
from apps.cmdb.services.ipam_view import build_ipam_view

pytestmark = pytest.mark.unit

SUBNET = {"_id": 9, "model_id": "subnet", "subnet_address": "10.0.1.0", "subnet_mask": "24"}
IPS = [
    {"_id": 101, "ip_addr": "10.0.1.10", "ip_status": ["online"], "ip_allocated_status": ["allocated"]},
    {"_id": 102, "ip_addr": "10.0.1.11", "ip_status": ["conflict"], "ip_allocated_status": ["allocated"]},
    {"_id": 103, "ip_addr": "10.0.1.12", "ip_status": ["unknown"], "ip_allocated_status": ["reserved"]},
]


class TestBuildIpamView:
    def test_容量与利用率(self):
        with patch("apps.cmdb.services.ipam_view._query_subnet_ips", return_value=IPS):
            out = build_ipam_view(SUBNET)
        assert out["capacity"] == 254
        assert out["used"] == 3
        assert out["available"] == 251

    def test_状态计数(self):
        with patch("apps.cmdb.services.ipam_view._query_subnet_ips", return_value=IPS):
            out = build_ipam_view(SUBNET)
        assert out["status_counts"]["online"] == 1
        assert out["status_counts"]["conflict"] == 1

    def test_ip列表带地址(self):
        with patch("apps.cmdb.services.ipam_view._query_subnet_ips", return_value=IPS):
            out = build_ipam_view(SUBNET)
        addrs = {ip["ip_addr"] for ip in out["ips"]}
        assert "10.0.1.10" in addrs
