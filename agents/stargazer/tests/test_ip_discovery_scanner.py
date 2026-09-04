# -- coding: utf-8 --
"""IP 发现 collector：TCP 判活、ICMP 判活、并发聚合、best-effort MAC。规格 §13.2/§13.3。"""

import asyncio
import importlib
from unittest.mock import patch

import pytest
from plugins.inputs.ip.ip_discovery_scanner import IPDiscoveryScanner

pytestmark = pytest.mark.unit
SUBNET_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


def _run(coro):
    return asyncio.run(coro)


async def _make_true():
    return True


class TestScanner:
    def test_单次探测超时不读取表单总预算(self):
        scanner = IPDiscoveryScanner(
            {
                "model_id": "ip",
                "scan_method": "icmp",
                "targets": ["10.0.1.10"],
                "timeout": 999,
            }
        )

        assert scanner.timeout == 5

    @pytest.mark.parametrize("port", [-1, 0, 65536, 22.5, True, "not-a-port"])
    def test_拒绝超出tcp端口值域的端口(self, port):
        with pytest.raises(ValueError, match="port must be between 1 and 65535"):
            IPDiscoveryScanner(
                {
                    "model_id": "ip",
                    "scan_method": "tcp",
                    "ports": [port],
                    "targets": ["10.0.1.10"],
                }
            )

    def test_tcp端口值域边界和数字字符串保持兼容(self):
        scanner = IPDiscoveryScanner(
            {
                "model_id": "ip",
                "scan_method": "tcp",
                "ports": [1, " 22 ", "+443", 65535],
                "targets": ["10.0.1.10"],
            }
        )

        assert scanner.ports == [1, 22, 443, 65535]

    def test_拒绝超过运行目标上限的子网(self, monkeypatch):
        monkeypatch.setenv("MAX_TARGETS_PER_RUN", "2")

        with pytest.raises(ValueError, match="MAX_TARGETS_PER_RUN"):
            IPDiscoveryScanner(
                {
                    "model_id": "ip",
                    "scan_method": "icmp",
                    "subnets": [{"subnet_uuid": SUBNET_UUID, "cidr": "10.0.1.0/29"}],
                }
            )

    def test_tcp_任一端口通即判活(self):
        scanner = IPDiscoveryScanner(
            {
                "model_id": "ip",
                "scan_method": "tcp",
                "ports": [22, 80],
                "targets": ["10.0.1.10", "10.0.1.11"],
            }
        )

        async def fake_tcp(ip, port, timeout):
            return ip == "10.0.1.10" and port == 22

        with patch.object(scanner, "_tcp_probe", side_effect=fake_tcp):
            out = _run(scanner.list_all_resources())
        alive = {r["ip"] for r in out["result"]["ip"]}
        assert alive == {"10.0.1.10"}
        assert out["success"] is True

    def test_icmp_判活(self):
        scanner = IPDiscoveryScanner(
            {
                "model_id": "ip",
                "scan_method": "icmp",
                "targets": ["10.0.1.10", "10.0.1.99"],
            }
        )

        async def fake_icmp(ip, timeout):
            return ip == "10.0.1.10"

        with patch.object(scanner, "_icmp_probe", side_effect=fake_icmp):
            out = _run(scanner.list_all_resources())
        assert {r["ip"] for r in out["result"]["ip"]} == {"10.0.1.10"}

    def test_结果带mac字段(self):
        scanner = IPDiscoveryScanner({"model_id": "ip", "scan_method": "icmp", "targets": ["10.0.1.10"]})

        async def fake_icmp(ip, timeout):
            return True

        async def fake_read_mac(_ip):
            return "00:0C:29:3A:7B:88"

        with patch.object(scanner, "_icmp_probe", side_effect=fake_icmp), patch.object(scanner, "_read_mac", side_effect=fake_read_mac):
            out = _run(scanner.list_all_resources())
        assert out["result"]["ip"][0]["mac"] == "00:0C:29:3A:7B:88"

    def test_从子网推导目标并输出ipam字段(self):
        scanner = IPDiscoveryScanner(
            {
                "model_id": "ip",
                "scan_method": "icmp",
                "subnets": [
                    {
                        "subnet_uuid": SUBNET_UUID,
                        "cidr": "10.0.1.0/30",
                        "gateway": "10.0.1.1",
                        "reserved_addresses": [],
                    }
                ],
            }
        )

        async def fake_icmp(ip, timeout):
            return ip == "10.0.1.2"

        async def fake_read_mac(_ip):
            return "00:0C:29:3A:7B:88"

        with patch.object(scanner, "_icmp_probe", side_effect=fake_icmp), patch.object(scanner, "_read_mac", side_effect=fake_read_mac):
            out = _run(scanner.list_all_resources())

        assert out["success"] is True
        assert out["result"]["ip"] == [
            {
                "ip_addr": "10.0.1.2",
                "ip_status": "online",
                "subnet_uuid": SUBNET_UUID,
                "subnet_cidr": "10.0.1.0/30",
                "scan_method": "icmp",
                "auto_collect": "true",
                "mac": "00:0C:29:3A:7B:88",
            }
        ]

    @pytest.mark.asyncio
    async def test_mac查询不阻塞事件循环(self):
        scanner = IPDiscoveryScanner(
            {
                "model_id": "ip",
                "scan_method": "icmp",
                "targets": ["10.0.1.10", "10.0.1.11"],
            }
        )
        ticks = 0

        async def fake_icmp(_ip, _timeout):
            return True

        async def slow_read_mac(_ip):
            await asyncio.sleep(0.05)
            return "00:0C:29:3A:7B:88"

        async def heartbeat():
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.005)

        heartbeat_task = asyncio.create_task(heartbeat())
        try:
            with patch.object(scanner, "_icmp_probe", side_effect=fake_icmp), patch.object(scanner, "_read_mac", side_effect=slow_read_mac):
                result = await scanner.list_all_resources()
        finally:
            heartbeat_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await heartbeat_task

        assert len(result["result"]["ip"]) == 2
        assert ticks >= 5

    @pytest.mark.asyncio
    async def test_mac查询使用异步子进程(self, monkeypatch):
        scanner = IPDiscoveryScanner({"model_id": "ip", "targets": ["10.0.1.10"]})
        calls = []

        class Process:
            returncode = 0

            async def communicate(self):
                return b"10.0.1.10 ether 00:0C:29:3A:7B:88 C eth0\n", b""

        async def create_subprocess(*args, **kwargs):
            calls.append((args, kwargs))
            return Process()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess)
        monkeypatch.setattr(scanner, "_icmp_probe", lambda *_args: _make_true())

        result = await scanner.list_all_resources()

        assert result["result"]["ip"][0]["mac"] == "00:0C:29:3A:7B:88"
        assert calls[0][0] == ("arp", "-n", "10.0.1.10")

    @pytest.mark.asyncio
    async def test_mac查询和探测共享同一并发边界(self, monkeypatch):
        scanner = IPDiscoveryScanner({"model_id": "ip", "targets": [f"10.0.1.{index}" for index in range(1, 8)]})
        scanner.concurrency = 2
        active = 0
        peak = 0

        async def fake_icmp(_ip, _timeout):
            return True

        async def fake_read_mac(_ip):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return ""

        monkeypatch.setattr(scanner, "_icmp_probe", fake_icmp)
        monkeypatch.setattr(scanner, "_read_mac", fake_read_mac)

        result = await scanner.list_all_resources()

        assert len(result["result"]["ip"]) == 7
        assert peak <= 2


def test_plugin_yml_loads_and_points_to_scanner():
    import os

    import yaml

    path = os.path.join(os.path.dirname(__file__), "..", "plugins", "inputs", "ip", "plugin.yml")
    cfg = yaml.safe_load(open(os.path.abspath(path), encoding="utf-8"))
    assert cfg["metadata"]["model_id"] == "ip"
    proto = cfg["executors"]["protocol"]
    assert proto["collector"]["class"] == "IPDiscoveryScanner"
    assert proto["collector"]["module"] == "plugins.inputs.ip.ip_discovery_scanner"
    collector_module = importlib.import_module(proto["collector"]["module"])
    assert getattr(collector_module, proto["collector"]["class"]) is IPDiscoveryScanner
