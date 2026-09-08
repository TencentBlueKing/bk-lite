# -*- coding: utf-8 -*-
"""对 mock 跑一遍 DellUnityManager，断言口采集与空身份保留在原始回包中。"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

STARGAZER_ROOT = Path(__file__).resolve().parents[2]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

from devtools.dell_unity_mock.server import DEFAULT_PASSWORD, DEFAULT_USERNAME, DellUnityMockServer  # noqa: E402


async def collect_against(server: DellUnityMockServer) -> dict:
    from plugins.inputs.dell_unity.dell_unity_info import DellUnityManager

    manager = DellUnityManager(
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


def assert_collect_payload(result: dict, server: DellUnityMockServer) -> None:
    assert result["success"] is True, result
    payload = result["result"]
    storage = payload["storage"][0]
    assert storage["device_sn"] == "FNM00123456789"
    assert storage["brand"] == "dell"
    assert storage["storage_type"] == "SAN"
    assert storage["model"] == "Unity 480"
    assert storage["firmware_version"] == "5.3.0.0.5.120"
    assert storage["pool_count"] == "1"
    assert storage["disk_count"] == "1"
    assert storage["volume_count"] == "2"
    assert len(payload["storage_pool"]) == 1
    assert payload["storage_pool"][0]["name"] == "Pool0"
    assert len(payload["storage_disk"]) == 1
    assert len(payload["storage_volume"]) == 2
    assert payload["storage_volume"][0]["wwn"]
    assert payload["storage_volume"][0]["parent_pool"] == "Pool0"
    eth_ports = payload["storage_eth_port"]
    assert len(eth_ports) == 3
    assert eth_ports[0]["macAddress"] == "00:60:16:aa:bb:01"
    assert eth_ports[1]["macAddress"] == ""
    assert eth_ports[2]["macAddress"] == "00-60-16-AA-BB-02"
    fc_ports = payload["storage_fc_port"]
    assert len(fc_ports) == 3
    assert fc_ports[0]["wwn"] == "50:06:01:60:88:60:32:8D"
    assert fc_ports[1]["wwn"] == ""
    assert fc_ports[2]["wwn"] == "500601608860328E"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="对 Dell Unity mock 跑采集冒烟")
    parser.add_argument("--tls", action="store_true")
    args = parser.parse_args(argv)
    with DellUnityMockServer(port=0, username=DEFAULT_USERNAME, password=DEFAULT_PASSWORD, tls=args.tls) as server:
        result = asyncio.run(collect_against(server))
        assert_collect_payload(result, server)
    print("dell unity mock smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
