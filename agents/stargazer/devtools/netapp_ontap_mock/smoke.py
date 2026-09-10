# -*- coding: utf-8 -*-
"""对 mock 跑一遍 NetAppOntapManager，断言口采集与空身份保留在原始回包中。"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

STARGAZER_ROOT = Path(__file__).resolve().parents[2]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

from devtools.netapp_ontap_mock.server import DEFAULT_PASSWORD, DEFAULT_USERNAME, NetAppOntapMockServer  # noqa: E402


async def collect_against(server: NetAppOntapMockServer) -> dict:
    from plugins.inputs.netapp_ontap.netapp_ontap_info import NetAppOntapManager

    manager = NetAppOntapManager(
        {
            "host": server.host,
            "port": server.port,
            "scheme": server.scheme,
            "username": server.username,
            "password": server.password,
            "verify_tls": False,
        }
    )
    return await manager.list_all_resources()


def assert_collect_payload(result: dict, server: NetAppOntapMockServer) -> None:
    assert result["success"] is True, result
    payload = result["result"]
    storage = payload["storage"][0]
    assert storage["device_sn"] == "1cd8a442-86d1-11e0-ae1c-123478563412"
    assert storage["brand"] == "netapp"
    assert storage["storage_type"] == "unified"
    assert storage["model"] == "AFF-A400"
    assert storage["firmware_version"].startswith("NetApp Release 9.13.1P1")
    assert storage["pool_count"] == "1"
    assert storage["disk_count"] == "1"
    assert storage["volume_count"] == "3"
    assert len(payload["storage_pool"]) == 1
    assert payload["storage_pool"][0]["name"] == "aggr1"
    assert len(payload["storage_disk"]) == 1
    assert len(payload["storage_volume"]) == 3
    assert all(not item.get("wwn") for item in payload["storage_volume"])
    eth_ports = payload["storage_eth_port"]
    assert len(eth_ports) == 3
    assert eth_ports[0]["mac_address"] == "00:0c:29:aa:bb:01"
    assert eth_ports[0]["ip_addr"] == "10.0.0.10"
    assert eth_ports[1]["mac_address"] == ""
    assert eth_ports[2]["mac_address"] == "00-0c-29-aa-bb-02"
    fc_ports = payload["storage_fc_port"]
    assert len(fc_ports) == 3
    assert fc_ports[0]["wwpn"] == "50:0a:09:81:80:11:22:33"
    assert fc_ports[1]["wwpn"] == ""
    assert fc_ports[2]["wwpn"] == "500a098180112234"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="对 NetApp ONTAP mock 跑采集冒烟")
    parser.add_argument("--tls", action="store_true")
    args = parser.parse_args(argv)
    with NetAppOntapMockServer(port=0, username=DEFAULT_USERNAME, password=DEFAULT_PASSWORD, tls=args.tls) as server:
        result = asyncio.run(collect_against(server))
        assert_collect_payload(result, server)
    print("netapp ontap mock smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
