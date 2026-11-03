from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping, Sequence

from core.logger import logger

_LINUX_PS = "ps -eo args --no-headers"
_WINDOWS_PS = "wmic process get CommandLine"
_AGENT_CREDENTIAL_ID = "agent"


def _ssh_item(host_login: Mapping[str, Any] | None) -> dict[str, Any] | None:
    pool = (host_login or {}).get("pool") if isinstance(host_login, Mapping) else None
    for item in pool or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("credential_id") or "").strip() == _AGENT_CREDENTIAL_ID:
            continue
        if item.get("credential_source") == "agent":
            continue
        if item.get("password") or item.get("private_key") or item.get("key") or item.get("key_filename"):
            return dict(item)
    return None


def _cloud_region_id(host_login: Mapping[str, Any] | None) -> Any:
    cloud_region = (host_login or {}).get("cloud_region") if isinstance(host_login, Mapping) else None
    if isinstance(cloud_region, dict):
        return cloud_region.get("id")
    return cloud_region


def _execution_id(host_login: Mapping[str, Any] | None) -> Any:
    if not isinstance(host_login, Mapping):
        return None
    value = host_login.get("execution_id")
    if value in (None, ""):
        value = host_login.get("collect_task_id")
    return value


def _access_point_id(access_point: Sequence[Any] | None) -> str:
    for item in access_point or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get("id") or item.get("node_id") or "").strip()
        if value:
            return value
    return ""


def _lines_from_output(raw: Any) -> list[str]:
    if isinstance(raw, dict):
        raw = raw.get("stdout") or raw.get("output") or raw.get("result") or ""
    return [line.strip() for line in str(raw or "").splitlines() if line.strip()]


def _ssh_exec_params(host: str, item: dict[str, Any], command: str) -> dict[str, Any]:
    try:
        port = int(item.get("port") or 22)
    except (TypeError, ValueError):
        port = 22
    username = str(item.get("username") or item.get("user") or "root")
    params: dict[str, Any] = {
        "command": command,
        "execute_timeout": 15,
        "host": host,
        "user": username,
        "username": username,
        "port": port if port > 0 else 22,
        "connection_test": True,
    }
    if item.get("password"):
        params["password"] = item.get("password")
    private_key = item.get("private_key") or item.get("key")
    if private_key:
        params["private_key"] = private_key
    if item.get("passphrase"):
        params["passphrase"] = item.get("passphrase")
    return params


async def list_scan_processes(
    host: str,
    host_login: Mapping[str, Any] | None = None,
    access_point: Sequence[Any] | None = None,
) -> list[str]:
    """每主机列一次进程。已纳管节点走 Agent local.execute；否则再走接入点 SSH。"""
    if _execution_id(host_login) not in (None, ""):
        lines = await _list_processes_agent(host, host_login)
        if lines:
            return lines
    item = _ssh_item(host_login)
    if item is None:
        return []
    node_id = _access_point_id(access_point)
    if node_id:
        return await _list_processes_ssh_nats(host, item, node_id)
    return await asyncio.to_thread(_list_processes_ssh, host, item)


def _list_processes_ssh(host: str, item: dict[str, Any]) -> list[str]:
    from core.infra.ssh_client import SSHClient

    try:
        port = int(item.get("port") or 22)
    except (TypeError, ValueError):
        port = 22
    client = SSHClient(timeout=int(item.get("timeout") or 15))
    try:
        client.connect(
            host=host,
            username=str(item.get("username") or item.get("user") or "root"),
            password=item.get("password") or None,
            port=port if port > 0 else 22,
            key_filename=item.get("key_filename") or None,
        )
        result = client.execute_command(_LINUX_PS, timeout=15)
        if result.exit_status != 0 or not str(result.stdout or "").strip():
            result = client.execute_command(_WINDOWS_PS, timeout=15)
        return _lines_from_output(result.stdout)
    except Exception as exc:
        logger.debug(
            "event=scan_process_ssh_failed host=%s failed_stage=ssh_ps error_type=%s",
            host,
            type(exc).__name__,
        )
        return []
    finally:
        client.close()


async def _list_processes_ssh_nats(host: str, item: dict[str, Any], node_id: str) -> list[str]:
    from core.infra.nats_utils import nats_request

    for command in (_LINUX_PS, _WINDOWS_PS):
        try:
            payload = json.dumps({"args": [_ssh_exec_params(host, item, command)], "kwargs": {}}).encode()
            response = await nats_request(f"ssh.execute.{node_id}", payload, timeout=20)
        except Exception as exc:
            logger.debug(
                "event=scan_process_ssh_nats_failed host=%s failed_stage=ssh_execute error_type=%s",
                host,
                type(exc).__name__,
            )
            return []
        if not isinstance(response, Mapping) or not response.get("success"):
            continue
        lines = _lines_from_output(response.get("result"))
        if lines:
            return lines
    return []


async def _list_processes_agent(host: str, host_login: Mapping[str, Any] | None) -> list[str]:
    collect_task_id = _execution_id(host_login)
    if collect_task_id in (None, ""):
        return []
    try:
        from service.node_info_loader import load_node_infos

        nodes = await load_node_infos(
            [host],
            collect_task_id=collect_task_id,
            cloud_region_id=_cloud_region_id(host_login),
        )
    except Exception as exc:
        logger.debug(
            "event=scan_process_agent_lookup_failed host=%s failed_stage=node_lookup error_type=%s",
            host,
            type(exc).__name__,
        )
        return []
    node = _node_for_host(nodes, host)
    if node is None:
        return []
    os_name = str(node.get("operating_system") or "").lower()
    if "win" in os_name:
        return []
    node_id = str(node.get("id") or "").strip()
    if not node_id:
        return []
    try:
        from core.infra.nats_utils import nats_request

        payload = json.dumps({"args": [{"command": _LINUX_PS, "execute_timeout": 15, "shell": "sh"}], "kwargs": {}}).encode()
        response = await nats_request(f"local.execute.{node_id}", payload, timeout=20)
    except Exception as exc:
        logger.debug(
            "event=scan_process_agent_exec_failed host=%s failed_stage=local_execute error_type=%s",
            host,
            type(exc).__name__,
        )
        return []
    if not isinstance(response, Mapping) or not response.get("success"):
        return []
    return _lines_from_output(response.get("result"))


def _node_for_host(nodes, host: str) -> Mapping[str, Any] | None:
    wanted = str(host or "").strip()
    for node in nodes or []:
        if not isinstance(node, Mapping):
            continue
        if str(node.get("ip") or "").strip() == wanted:
            return node
    for node in nodes or []:
        if isinstance(node, Mapping):
            return node
    return None
