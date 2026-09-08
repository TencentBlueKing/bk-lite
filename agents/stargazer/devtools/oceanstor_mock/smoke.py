# -*- coding: utf-8 -*-
"""对 mock 跑一遍 OceanStorManager，断言口采集与空身份保留在原始回包中。"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

STARGAZER_ROOT = Path(__file__).resolve().parents[2]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

from devtools.oceanstor_mock.server import DEFAULT_PASSWORD, DEFAULT_USERNAME, OceanStorMockServer  # noqa: E402


async def collect_against(server: OceanStorMockServer) -> dict:
    from plugins.inputs.oceanstor.oceanstor_info import OceanStorManager

    manager = OceanStorManager(
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


def assert_collect_payload(result: dict, server: OceanStorMockServer) -> None:
    assert result["success"] is True, result
    payload = result["result"]
    storage = payload["storage"][0]
    assert storage["device_sn"] == server.device_id
    assert storage["model"] == "Dorado 5000 V6"
    assert storage["firmware_version"] == "V600R003C00"
    assert storage["pool_count"] == "1"
    assert storage["disk_count"] == "1"
    assert storage["volume_count"] == "1"
    assert len(payload["storage_pool"]) == 1
    assert payload["storage_pool"][0]["NAME"] == "StoragePool001"
    assert len(payload["storage_disk"]) == 1
    assert len(payload["storage_volume"]) == 1
    eth_ports = payload["storage_eth_port"]
    assert len(eth_ports) == 3
    assert eth_ports[0]["MACADDR"] == "AA-BB-CC-DD-EE-01"
    assert eth_ports[0]["IPV4ADDR"] == "10.0.1.8"
    assert eth_ports[1]["MACADDR"] == ""
    assert eth_ports[1].get("MACADDRESS") in (None, "")
    assert eth_ports[2].get("MACADDR") in (None, "")
    assert eth_ports[2]["MACADDRESS"] == "AA-BB-CC-DD-EE-02"
    fc_ports = payload["storage_fc_port"]
    assert len(fc_ports) == 3
    assert fc_ports[0]["WWPN"] == "21000024FF5A1234"
    assert fc_ports[1]["WWPN"] == "--"
    assert fc_ports[2].get("WWPN") in (None, "")
    assert fc_ports[2]["WWN"] == "21000024FF5A1235"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="对 OceanStor mock 跑采集冒烟")
    parser.add_argument("--tls", action="store_true")
    args = parser.parse_args(argv)
    with OceanStorMockServer(port=0, username=DEFAULT_USERNAME, password=DEFAULT_PASSWORD, tls=args.tls) as server:
        result = asyncio.run(collect_against(server))
        assert_collect_payload(result, server)
    print("oceanstor mock smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
