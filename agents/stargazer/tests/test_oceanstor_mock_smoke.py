# -*- coding: utf-8 -*-
"""对真实 HTTP mock 跑 OceanStorManager，校验会话、池盘卷与口采集回包。"""
import sys
from pathlib import Path

import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

from devtools.oceanstor_mock.server import DEFAULT_PASSWORD, DEFAULT_USERNAME, OceanStorMockServer  # noqa: E402
from devtools.oceanstor_mock.smoke import assert_collect_payload, collect_against  # noqa: E402


def _port_identity():
    repo_root = Path(__file__).resolve().parents[3]
    server_root = repo_root / "server"
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))
    from apps.cmdb.collection.storage_port_inventory import eth_port_identity, fc_port_identity

    return eth_port_identity, fc_port_identity


@pytest.mark.asyncio
async def test_oceanstor_manager_collects_from_http_mock():
    eth_port_identity, fc_port_identity = _port_identity()
    with OceanStorMockServer(port=0, username=DEFAULT_USERNAME, password=DEFAULT_PASSWORD) as server:
        result = await collect_against(server)
        assert_collect_payload(result, server)
        assert result["result"]["storage"][0]["ip_addr"] == server.host
        eth_ports = result["result"]["storage_eth_port"]
        fc_ports = result["result"]["storage_fc_port"]
        assert [eth_port_identity(item) for item in eth_ports] == ["aa:bb:cc:dd:ee:01", "", "aa:bb:cc:dd:ee:02"]
        assert [fc_port_identity(item) for item in fc_ports] == ["21:00:00:24:ff:5a:12:34", "", "21:00:00:24:ff:5a:12:35"]
        empty_eth = next(item for item in eth_ports if item["NAME"] == "CTE0.A.IOM0.P1")
        empty_fc = next(item for item in fc_ports if item["NAME"] == "CTE0.A.IOM1.P1")
        assert empty_eth["MACADDR"] == ""
        assert eth_port_identity({"NAME": empty_eth["NAME"], "LOCATION": empty_eth["LOCATION"]}) == ""
        assert eth_port_identity(empty_eth) == ""
        assert fc_port_identity(empty_fc) == ""
        kept_eth = [item for item in eth_ports if eth_port_identity(item)]
        kept_fc = [item for item in fc_ports if fc_port_identity(item)]
        assert [eth_port_identity(item) for item in kept_eth] == ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"]
        assert [fc_port_identity(item) for item in kept_fc] == ["21:00:00:24:ff:5a:12:34", "21:00:00:24:ff:5a:12:35"]


@pytest.mark.asyncio
async def test_oceanstor_mock_rejects_bad_password():
    from plugins.inputs.oceanstor.oceanstor_info import OceanStorManager

    with OceanStorMockServer(port=0) as server:
        manager = OceanStorManager(
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


@pytest.mark.asyncio
async def test_oceanstor_mock_paginates_list_endpoints():
    from plugins.inputs.oceanstor.oceanstor_info import OceanStorManager

    original = OceanStorManager.PAGE_SIZE
    OceanStorManager.PAGE_SIZE = 1
    try:
        with OceanStorMockServer(port=0) as server:
            manager = OceanStorManager(
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
        OceanStorManager.PAGE_SIZE = original

    assert result["success"] is True
    assert len(result["result"]["storage_eth_port"]) == 3
    assert len(result["result"]["storage_fc_port"]) == 3
