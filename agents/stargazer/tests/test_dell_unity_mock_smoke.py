# -*- coding: utf-8 -*-
"""对真实 HTTP mock 跑 DellUnityManager，校验 Basic、REST Client 头与口采集回包。"""
import sys
from pathlib import Path

import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

from devtools.dell_unity_mock.server import DEFAULT_PASSWORD, DEFAULT_USERNAME, DellUnityMockServer  # noqa: E402
from devtools.dell_unity_mock.smoke import assert_collect_payload, collect_against  # noqa: E402


def _port_identity():
    repo_root = Path(__file__).resolve().parents[3]
    server_root = repo_root / "server"
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))
    from apps.cmdb.collection.storage_port_inventory import normalize_storage_mac, normalize_wwpn

    return normalize_storage_mac, normalize_wwpn


@pytest.mark.asyncio
async def test_dell_unity_manager_collects_from_http_mock():
    normalize_storage_mac, normalize_wwpn = _port_identity()
    with DellUnityMockServer(port=0, username=DEFAULT_USERNAME, password=DEFAULT_PASSWORD) as server:
        result = await collect_against(server)
        assert_collect_payload(result, server)
        eth_ports = result["result"]["storage_eth_port"]
        fc_ports = result["result"]["storage_fc_port"]
        assert [normalize_storage_mac(item.get("macAddress")) for item in eth_ports] == [
            "00:60:16:aa:bb:01",
            "",
            "00:60:16:aa:bb:02",
        ]
        assert [normalize_wwpn(item.get("wwn")) for item in fc_ports] == [
            "50:06:01:60:88:60:32:8d",
            "",
            "50:06:01:60:88:60:32:8e",
        ]
        assert all(item.get("wwn") for item in result["result"]["storage_volume"])


@pytest.mark.asyncio
async def test_dell_unity_mock_rejects_bad_password():
    from plugins.inputs.dell_unity.dell_unity_info import DellUnityManager

    with DellUnityMockServer(port=0) as server:
        manager = DellUnityManager(
            {
                "host": server.host,
                "port": server.port,
                "scheme": "http",
                "username": server.username,
                "password": "wrong-password",
                "verify_tls": False,
            }
        )
        result = await manager.list_all_resources()
        assert result["success"] is False
        assert "cmdb_collect_error" in result["result"]
        assert "wrong-password" not in str(result["result"])


@pytest.mark.asyncio
async def test_dell_unity_mock_paginates_list_endpoints():
    from plugins.inputs.dell_unity.dell_unity_info import DellUnityManager

    original = DellUnityManager.PAGE_SIZE
    DellUnityManager.PAGE_SIZE = 1
    try:
        with DellUnityMockServer(port=0) as server:
            manager = DellUnityManager(
                {
                    "host": server.host,
                    "port": server.port,
                    "scheme": "http",
                    "username": server.username,
                    "password": server.password,
                    "verify_tls": False,
                }
            )
            result = await manager.list_all_resources()
    finally:
        DellUnityManager.PAGE_SIZE = original

    assert result["success"] is True
    assert len(result["result"]["storage_eth_port"]) == 3
    assert len(result["result"]["storage_fc_port"]) == 3
    assert len(result["result"]["storage_volume"]) == 2
