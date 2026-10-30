"""用直连区域的真实 IP 走一遍 Job 三类执行，并核对 IP 预检会看到的端口。

凭据只从本机 Stargazer 环境读取，断言失败时去掉 URL 里的账号。
"""

import json
import os
import re
import ssl
from pathlib import Path

import pytest

ACCESS_POINT_IP = "172.18.0.30"
ACCESS_POINT_ID = "8d41f0d8a12811f1a1920242ac120010"
LINUX_NODE_IP = "10.10.41.149"
LINUX_NODE_ID = "99db84ff4339493686899ef94cf48f34"
WINDOWS_NODE_IP = "10.10.41.98"
WINDOWS_NODE_ID = "62156872bd35483795253de3339189b9"
UNMANAGED_IP = "192.0.2.50"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def _load_env():
    if os.environ.get("JOB_CHAIN_LIVE") != "1":
        pytest.skip("set JOB_CHAIN_LIVE=1 to run live NATS checks")
    if not ENV_PATH.exists():
        pytest.skip("stargazer env is not available")
    values = {}
    for line in ENV_PATH.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    url = values.get("NATS_URLS", "")
    ca_file = values.get("NATS_TLS_CA_FILE", "")
    if not url or not Path(ca_file).exists():
        pytest.skip("live NATS endpoint is not configured")
    return url, ca_file


def _public_error(error: BaseException) -> str:
    text = re.sub(r"//[^/\s@]+@", "//***@", str(error))
    return f"{type(error).__name__}: {text}"


async def _connect():
    import nats

    url, ca_file = _load_env()
    context = ssl.create_default_context(cafile=ca_file)
    context.check_hostname = False
    try:
        return await nats.connect(url, tls=context, allow_reconnect=False, connect_timeout=8)
    except Exception as error:
        raise AssertionError(_public_error(error)) from None


async def _request(client, subject, args, *, timeout):
    payload = json.dumps({"args": [args], "kwargs": {}}).encode()
    try:
        message = await client.request(subject, payload, timeout=timeout)
    except Exception as error:
        raise AssertionError(f"{subject} {_public_error(error)}") from None
    body = json.loads(message.data.decode())
    if isinstance(body, dict) and "result" in body and "success" in body and "instance_id" not in body:
        if body.get("success") is False:
            raise AssertionError(f"{subject} rejected: {body.get('error') or body.get('message') or 'failed'}")
        return body.get("result")
    return body


def _rows(result):
    if isinstance(result, dict):
        for key in ("items", "data", "results", "nodes"):
            value = result.get(key)
            if isinstance(value, list):
                return value
        return []
    return result if isinstance(result, list) else []


def _executor_running(node):
    status = node.get("status") if isinstance(node, dict) else None
    collectors = status.get("collectors") if isinstance(status, dict) else None
    if not isinstance(collectors, list):
        return False
    for collector in collectors:
        if not isinstance(collector, dict):
            continue
        collector_id = str(collector.get("collector_id") or "").strip().lower()
        if collector_id.startswith("natsexecutor") and collector.get("status") == 0:
            return True
    return False


async def _node(client, ip):
    result = await _request(
        client,
        "bklite.node_list",
        {
            "ip": ip,
            "page": 1,
            "page_size": 20,
            "skip_permission": True,
            "legacy_callsite": "stargazer.node_info",
        },
        timeout=15,
    )
    matches = [row for row in _rows(result) if str(row.get("ip") or "") == ip]
    return matches


async def _local_hostname(client, node_id, *, shell):
    body = await _request(
        client,
        f"local.execute.{node_id}",
        {"command": "hostname", "execute_timeout": 15, "shell": shell},
        timeout=20,
    )
    assert body.get("success") is True
    assert body.get("instance_id") == node_id
    return str(body.get("result") or "").strip()


@pytest.mark.asyncio
async def test_live_nodes_share_cloud_region_and_running_executor():
    client = await _connect()
    try:
        access_point, linux_node, windows_node, unmanaged = [
            await _node(client, ip) for ip in (ACCESS_POINT_IP, LINUX_NODE_IP, WINDOWS_NODE_IP, UNMANAGED_IP)
        ]
    finally:
        await client.close()

    assert [row["id"] for row in access_point] == [ACCESS_POINT_ID]
    assert [row["id"] for row in linux_node] == [LINUX_NODE_ID]
    assert [row["id"] for row in windows_node] == [WINDOWS_NODE_ID]
    assert unmanaged == []
    regions = {row.get("cloud_region_id") or row.get("cloud_region") for row in (*access_point, *linux_node, *windows_node)}
    assert regions == {1} or regions == {"1"}
    assert all(_executor_running(row) for row in (*access_point, *linux_node, *windows_node))


@pytest.mark.asyncio
async def test_live_access_point_executes_locally():
    client = await _connect()
    try:
        hostname = await _local_hostname(client, ACCESS_POINT_ID, shell="bash")
    finally:
        await client.close()
    assert hostname == "fusion-collector-default"


@pytest.mark.asyncio
async def test_live_same_region_linux_node_executes_locally():
    client = await _connect()
    try:
        hostname = await _local_hostname(client, LINUX_NODE_ID, shell="bash")
    finally:
        await client.close()
    assert hostname == "weops-lite"


@pytest.mark.asyncio
async def test_live_same_region_windows_node_executes_locally():
    client = await _connect()
    try:
        hostname = await _local_hostname(client, WINDOWS_NODE_ID, shell="powershell")
    finally:
        await client.close()
    assert hostname == "LAPTOP-T9UK50I2"


@pytest.mark.asyncio
async def test_live_unmanaged_ip_is_handled_by_access_point_ssh():
    client = await _connect()
    try:
        body = await _request(
            client,
            f"ssh.execute.{ACCESS_POINT_ID}",
            {
                "command": "hostname",
                "execute_timeout": 5,
                "host": UNMANAGED_IP,
                "user": "chain-test",
                "username": "chain-test",
                "password": "chain-test",
                "port": 22,
            },
            timeout=12,
        )
    finally:
        await client.close()

    assert body.get("instance_id") == ACCESS_POINT_ID
    assert body.get("success") is False
    detail = f"{body.get('code') or ''} {body.get('error') or body.get('result') or ''}".lower()
    assert any(marker in detail for marker in ("timeout", "timed out", "refused", "no route", "unreachable", "failed"))


@pytest.mark.asyncio
async def test_live_ip_precheck_from_access_point_sees_windows_ssh_closed_and_linux_ssh_open():
    client = await _connect()
    try:
        body = await _request(
            client,
            f"local.execute.{ACCESS_POINT_ID}",
            {
                "command": (
                    'probe() { timeout 3 bash -c "echo >/dev/tcp/$1/22" >/dev/null 2>&1 && echo "$1 OPEN" || echo "$1 FAIL"; }; '
                    f"probe {WINDOWS_NODE_IP}; probe {LINUX_NODE_IP}"
                ),
                "execute_timeout": 15,
                "shell": "bash",
            },
            timeout=20,
        )
    finally:
        await client.close()

    assert body.get("success") is True
    output = str(body.get("result") or "")
    assert f"{WINDOWS_NODE_IP} FAIL" in output
    assert f"{LINUX_NODE_IP} OPEN" in output
