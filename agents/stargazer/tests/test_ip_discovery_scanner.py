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
