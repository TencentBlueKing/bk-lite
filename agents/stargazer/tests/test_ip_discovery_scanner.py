# -- coding: utf-8 --
"""IP 发现 collector：TCP 判活、ICMP 判活、并发聚合、best-effort MAC。规格 §13.2/§13.3。"""
import asyncio
import pytest
from unittest.mock import patch
from plugins.inputs.ip_discovery.ip_discovery_scanner import IPDiscoveryScanner

pytestmark = pytest.mark.unit


def _run(coro):
    return asyncio.run(coro)


async def _make_true():
    return True


class TestScanner:
    def test_tcp_任一端口通即判活(self):
        scanner = IPDiscoveryScanner({
            "model_id": "ip", "scan_method": "tcp", "ports": [22, 80],
            "targets": ["10.0.1.10", "10.0.1.11"],
        })

        async def fake_tcp(ip, port, timeout):
            return ip == "10.0.1.10" and port == 22

        with patch.object(scanner, "_tcp_probe", side_effect=fake_tcp):
            out = _run(scanner.list_all_resources())
        alive = {r["ip"] for r in out["result"]["ip"]}
        assert alive == {"10.0.1.10"}
        assert out["success"] is True

    def test_icmp_判活(self):
        scanner = IPDiscoveryScanner({
            "model_id": "ip", "scan_method": "icmp", "targets": ["10.0.1.10", "10.0.1.99"],
        })

        async def fake_icmp(ip, timeout):
            return ip == "10.0.1.10"

        with patch.object(scanner, "_icmp_probe", side_effect=fake_icmp):
            out = _run(scanner.list_all_resources())
        assert {r["ip"] for r in out["result"]["ip"]} == {"10.0.1.10"}

    def test_结果带mac字段(self):
        scanner = IPDiscoveryScanner({"model_id": "ip", "scan_method": "icmp", "targets": ["10.0.1.10"]})

        async def fake_icmp(ip, timeout):
            return True

        with patch.object(scanner, "_icmp_probe", side_effect=fake_icmp), \
             patch.object(scanner, "_read_mac", side_effect=lambda ip: "00:0C:29:3A:7B:88"):
            out = _run(scanner.list_all_resources())
        assert out["result"]["ip"][0]["mac"] == "00:0C:29:3A:7B:88"

    def test_从子网推导目标并输出ipam字段(self):
        scanner = IPDiscoveryScanner({
            "model_id": "ip",
            "scan_method": "icmp",
            "subnets": [
                {
                    "subnet_id": 101,
                    "cidr": "10.0.1.0/30",
                    "gateway": "10.0.1.1",
                    "reserved_addresses": [],
                }
            ],
        })

        async def fake_icmp(ip, timeout):
            return ip == "10.0.1.2"

        with patch.object(scanner, "_icmp_probe", side_effect=fake_icmp), \
             patch.object(scanner, "_read_mac", side_effect=lambda ip: "00:0C:29:3A:7B:88"):
            out = _run(scanner.list_all_resources())

        assert out["success"] is True
        assert out["result"]["ip"] == [
            {
                "ip_addr": "10.0.1.2",
                "ip_status": "online",
                "subnet_id": "101",
                "subnet_cidr": "10.0.1.0/30",
                "scan_method": "icmp",
                "auto_collect": "true",
                "mac": "00:0C:29:3A:7B:88",
            }
        ]


def test_plugin_yml_loads_and_points_to_scanner():
    import os, yaml
    path = os.path.join(os.path.dirname(__file__), "..", "plugins", "inputs", "ip_discovery", "plugin.yml")
    cfg = yaml.safe_load(open(os.path.abspath(path), encoding="utf-8"))
    assert cfg["metadata"]["model_id"] == "ip"
    proto = cfg["executors"]["protocol"]
    assert proto["collector"]["class"] == "IPDiscoveryScanner"
    assert proto["collector"]["module"].endswith("ip_discovery_scanner")
