# -- coding: utf-8 --
"""IP 发现 NATS handler 单元测试。规格 §13。

测试策略：
- monkeypatch IPDiscoveryScanner.list_all_resources 返回已知存活列表
- monkeypatch _publish_ip_discovery_result 避免真实 NATS 连接
- 验证 handle_ip_scan 产出正确的 {"subnet_id": ..., "alive": [...]} 结构
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

pytestmark = pytest.mark.unit


FAKE_PAYLOAD = {
    "model_id": "ip",
    "subnet_id": 42,
    "scan_method": "icmp",
    "ports": [22, 80, 443, 3389],
    "targets": ["10.0.1.2", "10.0.1.3", "10.0.1.4"],
    "callback_subject": "receive_ip_discovery_result",
}

FAKE_ALIVE = [
    {"ip": "10.0.1.2", "mac": "AA:BB:CC:DD:EE:01"},
    {"ip": "10.0.1.4", "mac": ""},
]


def _run(coro):
    return asyncio.run(coro)


class TestHandleIpScan:
    def test_正常扫描返回subnet_id和alive列表(self):
        from plugins.inputs.ip_discovery.ip_discovery_handler import handle_ip_scan

        fake_scan_result = {"success": True, "result": {"ip": FAKE_ALIVE}}

        with patch(
            "plugins.inputs.ip_discovery.ip_discovery_handler._publish_ip_discovery_result",
            new_callable=AsyncMock,
        ) as mock_publish, patch(
            "plugins.inputs.ip_discovery.ip_discovery_handler.IPDiscoveryScanner"
        ) as MockScanner:
            instance = MagicMock()
            instance.list_all_resources = AsyncMock(return_value=fake_scan_result)
            MockScanner.return_value = instance

            result = _run(handle_ip_scan(FAKE_PAYLOAD))

        assert result["subnet_id"] == 42
        assert result["alive"] == FAKE_ALIVE
        mock_publish.assert_awaited_once_with(
            "receive_ip_discovery_result",
            {"subnet_id": 42, "alive": FAKE_ALIVE},
        )

    def test_扫描异常时返回空alive列表(self):
        from plugins.inputs.ip_discovery.ip_discovery_handler import handle_ip_scan

        with patch(
            "plugins.inputs.ip_discovery.ip_discovery_handler._publish_ip_discovery_result",
            new_callable=AsyncMock,
        ), patch(
            "plugins.inputs.ip_discovery.ip_discovery_handler.IPDiscoveryScanner"
        ) as MockScanner:
            instance = MagicMock()
            instance.list_all_resources = AsyncMock(side_effect=RuntimeError("network error"))
            MockScanner.return_value = instance

            result = _run(handle_ip_scan(FAKE_PAYLOAD))

        assert result["subnet_id"] == 42
        assert result["alive"] == []

    def test_缺少subnet_id时仍可正常运行(self):
        from plugins.inputs.ip_discovery.ip_discovery_handler import handle_ip_scan

        payload_no_id = {**FAKE_PAYLOAD, "subnet_id": None}
        fake_scan_result = {"success": True, "result": {"ip": []}}

        with patch(
            "plugins.inputs.ip_discovery.ip_discovery_handler._publish_ip_discovery_result",
            new_callable=AsyncMock,
        ), patch(
            "plugins.inputs.ip_discovery.ip_discovery_handler.IPDiscoveryScanner"
        ) as MockScanner:
            instance = MagicMock()
            instance.list_all_resources = AsyncMock(return_value=fake_scan_result)
            MockScanner.return_value = instance

            result = _run(handle_ip_scan(payload_no_id))

        assert result["subnet_id"] is None
        assert result["alive"] == []

    def test_publish失败时handler不抛出异常(self):
        """publish 失败（NATS 断开等）不应导致 handler 崩溃。"""
        from plugins.inputs.ip_discovery.ip_discovery_handler import handle_ip_scan

        fake_scan_result = {"success": True, "result": {"ip": FAKE_ALIVE}}

        with patch(
            "plugins.inputs.ip_discovery.ip_discovery_handler._publish_ip_discovery_result",
            new_callable=AsyncMock,
            side_effect=ConnectionError("NATS not connected"),
        ), patch(
            "plugins.inputs.ip_discovery.ip_discovery_handler.IPDiscoveryScanner"
        ) as MockScanner:
            instance = MagicMock()
            instance.list_all_resources = AsyncMock(return_value=fake_scan_result)
            MockScanner.return_value = instance

            # 不应抛出异常
            result = _run(handle_ip_scan(FAKE_PAYLOAD))

        assert result["subnet_id"] == 42
        assert result["alive"] == FAKE_ALIVE


class TestPublishIpDiscoveryResult:
    def test_publish按nats约定格式封装payload(self):
        """_publish_ip_discovery_result 应将 data 包装为 {"args": [], "kwargs": {"data": ...}}
        并发送到 {NATS_NAMESPACE}.{callback_subject}。
        """
        import os
        from plugins.inputs.ip_discovery.ip_discovery_handler import _publish_ip_discovery_result

        result_data = {"subnet_id": 42, "alive": FAKE_ALIVE}

        with patch(
            "plugins.inputs.ip_discovery.ip_discovery_handler.nats_publish",
            new_callable=AsyncMock,
        ) as mock_pub, patch.dict(os.environ, {"NATS_NAMESPACE": "bklite"}):
            _run(_publish_ip_discovery_result("receive_ip_discovery_result", result_data))

        mock_pub.assert_awaited_once_with(
            "bklite.receive_ip_discovery_result",
            {"args": [], "kwargs": {"data": result_data}},
        )
