# -*- coding: utf-8 -*-
"""对真实 HTTP mock 跑 NetAppOntapManager，校验 Basic、池盘卷与口采集回包。"""
import sys
from pathlib import Path

import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

from devtools.netapp_ontap_mock.server import DEFAULT_PASSWORD, DEFAULT_USERNAME, NetAppOntapMockServer  # noqa: E402
from devtools.netapp_ontap_mock.smoke import assert_collect_payload, collect_against  # noqa: E402


def _port_identity():
    repo_root = Path(__file__).resolve().parents[3]
    server_root = repo_root / "server"
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))
    from apps.cmdb.collection.storage_port_inventory import normalize_storage_mac, normalize_wwpn

    return normalize_storage_mac, normalize_wwpn


@pytest.mark.asyncio
async def test_netapp_ontap_manager_collects_from_http_mock():
    normalize_storage_mac, normalize_wwpn = _port_identity()
    with NetAppOntapMockServer(port=0, username=DEFAULT_USERNAME, password=DEFAULT_PASSWORD) as server:
        result = await collect_against(server)
        assert_collect_payload(result, server)
        eth_ports = result["result"]["storage_eth_port"]
        fc_ports = result["result"]["storage_fc_port"]
        assert [normalize_storage_mac(item.get("mac_address")) for item in eth_ports] == [
            "00:0c:29:aa:bb:01",
            "",
            "00:0c:29:aa:bb:02",
        ]
        assert [normalize_wwpn(item.get("wwpn")) for item in fc_ports] == [
            "50:0a:09:81:80:11:22:33",
            "",
            "50:0a:09:81:80:11:22:34",
        ]
        assert all(not item.get("wwn") for item in result["result"]["storage_volume"])


@pytest.mark.asyncio
async def test_netapp_ontap_mock_rejects_bad_password():
    from plugins.inputs.netapp_ontap.netapp_ontap_info import NetAppOntapManager

    with NetAppOntapMockServer(port=0) as server:
        manager = NetAppOntapManager(
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
async def test_netapp_ontap_mock_paginates_list_endpoints():
    from plugins.inputs.netapp_ontap.netapp_ontap_info import NetAppOntapManager

    original = NetAppOntapManager.PAGE_SIZE
    NetAppOntapManager.PAGE_SIZE = 1
    try:
        with NetAppOntapMockServer(port=0) as server:
            manager = NetAppOntapManager(
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
        NetAppOntapManager.PAGE_SIZE = original

    assert result["success"] is True
    assert len(result["result"]["storage_eth_port"]) == 3
    assert len(result["result"]["storage_fc_port"]) == 3
    assert len(result["result"]["storage_volume"]) == 3
