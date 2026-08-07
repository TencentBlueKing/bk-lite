"""
独立探测：4 台真实 SNMP 主机网络/协议是否通。

不经过 CollectionRuntime / CredentialAttempt 框架，只做：
1) UDP/SNMP GET sysName（1.3.6.1.2.1.1.5.0）
2) 打印每台耗时与结果

用法（在 agents/stargazer 下）::

    .venv/bin/pytest -q -o addopts='' -s tests/test_snmp_four_hosts_connectivity.py

注意：本文件含本地联调凭据，不要提交到远端。
"""

from __future__ import annotations

import socket
import time

import pytest
from pysnmp.entity.rfc3413.oneliner import cmdgen

SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"

# 用户提供的本地联调目标（勿入库/勿推远程）
TARGETS = (
    {
        "host": "10.10.69.247",
        "version": "v2",
        "community": "WeOps2024",
        "snmp_port": 161,
        "timeout": 20,
        "retries": 3,
    },
    {
        "host": "10.10.69.245",
        "version": "v2",
        "community": "WeOps2024",
        "snmp_port": 161,
        "timeout": 5,
        "retries": 1,
    },
    {
        "host": "10.10.69.248",
        "version": "v2",
        "community": "WeOps2024",
        "snmp_port": 161,
        "timeout": 5,
        "retries": 1,
    },
    {
        "host": "10.10.69.246",
        "version": "v2",
        "community": "WeCis@2024",
        "snmp_port": 161,
        "timeout": 5,
        "retries": 1,
    },
)


def _udp_probe(host: str, port: int, timeout: float = 2.0) -> dict:
    """发一个空 UDP 包，看本机能否把包送出去（不等同 SNMP 可达）。"""
    started = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(b"\x00", (host, port))
        return {
            "ok": True,
            "detail": "udp_send_ok",
            "elapsed": round(time.monotonic() - started, 3),
        }
    except OSError as error:
        return {
            "ok": False,
            "detail": f"udp_send_failed:{error}",
            "elapsed": round(time.monotonic() - started, 3),
        }
    finally:
        sock.close()


def _snmp_sysname_get(params: dict) -> dict:
    host = params["host"]
    port = int(params["snmp_port"])
    timeout = float(params.get("timeout") or 5)
    retries = int(params.get("retries") or 1)
    community = str(params["community"])
    started = time.monotonic()
    cmd_gen = cmdgen.CommandGenerator()
    try:
        error_indication, error_status, error_index, var_binds = cmd_gen.getCmd(
            cmdgen.CommunityData(community),
            cmdgen.UdpTransportTarget((host, port), timeout=timeout, retries=retries),
            cmdgen.MibVariable(SYS_NAME_OID),
            lookupMib=False,
        )
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "sys_name": "",
            "detail": f"exception:{type(error).__name__}:{error}",
            "elapsed": round(time.monotonic() - started, 3),
        }

    elapsed = round(time.monotonic() - started, 3)
    if error_indication:
        return {
            "ok": False,
            "sys_name": "",
            "detail": f"indication:{error_indication}",
            "elapsed": elapsed,
        }
    if error_status:
        return {
            "ok": False,
            "sys_name": "",
            "detail": f"status:{error_status.prettyPrint()}@{error_index}",
            "elapsed": elapsed,
        }
    if not var_binds:
        return {
            "ok": False,
            "sys_name": "",
            "detail": "empty_var_binds",
            "elapsed": elapsed,
        }
    sys_name = str(var_binds[0][1])
    return {
        "ok": True,
        "sys_name": sys_name,
        "detail": "sysName_ok",
        "elapsed": elapsed,
    }


@pytest.mark.parametrize("params", TARGETS, ids=lambda item: item["host"])
def test_snmp_host_is_reachable(params):
    host = params["host"]
    port = int(params["snmp_port"])
    udp = _udp_probe(host, port)
    snmp = _snmp_sysname_get(params)
    print(
        f"\n[{host}:{port}] udp={udp} snmp={snmp} "
        f"community_len={len(str(params['community']))}"
    )
    assert snmp["ok"], (
        f"{host} SNMP 不通: detail={snmp['detail']} elapsed={snmp['elapsed']}s "
        f"udp={udp}"
    )


def test_all_four_hosts_report():
    """汇总跑一遍，便于一眼看通断。"""
    rows = []
    for params in TARGETS:
        snmp = _snmp_sysname_get(params)
        rows.append(
            {
                "host": params["host"],
                "ok": snmp["ok"],
                "sys_name": snmp["sys_name"],
                "detail": snmp["detail"],
                "elapsed": snmp["elapsed"],
            }
        )
    print("\n=== SNMP four-host summary ===")
    for row in rows:
        status = "PASS" if row["ok"] else "FAIL"
        print(
            f"{status} {row['host']} elapsed={row['elapsed']}s "
            f"sysName={row['sys_name']!r} detail={row['detail']}"
        )
    failed = [row["host"] for row in rows if not row["ok"]]
    assert not failed, f"不通的主机: {failed}"
