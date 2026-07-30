"""沿补丁真实执行链路探测目标机连通性。"""

import io
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from apps.core.mixinx import EncryptMixin
from apps.patch_mgmt.constants import OSType
from apps.patch_mgmt.models import PatchTarget
from apps.patch_mgmt.services.target_execution_route import (
    TargetExecutionRoute,
    TargetExecutorUnavailable,
    TargetTransport,
    resolve_target_execution_route,
)
from apps.rpc.ansible import AnsibleExecutor
from apps.rpc.executor import Executor

logger = logging.getLogger("app")

PROBE_MARKER = "patch-connectivity-ok"
PROBE_TIMEOUT = 10
ANSIBLE_PROBE_TIMEOUT = 30
ANSIBLE_QUERY_INTERVAL = 0.2
_SECRET_RE = re.compile(
    r"(?i)(['\"]?(?:password|passwd|pwd|token|secret)['\"]?\s*[:=]\s*)"
    r"(?:['\"][^'\"]*['\"]|\S+)"
)


@dataclass(frozen=True)
class TargetProbeResult:
    reachable: bool
    port: Optional[int]
    detail: str
    transport: str = "unknown"
    stage: str = "command"
    reason_code: str = ""


def probe_target(target: PatchTarget) -> TargetProbeResult:
    """使用目标中已保存的配置，沿真实补丁执行链路测试。"""
    return probe_target_data(target_connection_data(target))


def target_connection_data(target: PatchTarget) -> dict:
    """将已保存目标转换为进程内即时使用的明文连接参数。"""
    data = {
        "id": target.id,
        "ip": target.ip,
        "os_type": target.os_type,
        "source_type": target.source_type,
        "node_id": target.node_id,
        "cloud_region_id": target.cloud_region_id,
        "ssh_port": target.ssh_port,
        "ssh_user": target.ssh_user,
        "ssh_credential_type": target.ssh_credential_type,
        "ssh_password": target.ssh_password,
        "ssh_key_passphrase": target.ssh_key_passphrase,
        "winrm_port": target.winrm_port,
        "winrm_scheme": target.winrm_scheme,
        "winrm_transport": target.winrm_transport,
        "winrm_user": target.winrm_user,
        "winrm_password": target.winrm_password,
        "winrm_cert_validation": target.winrm_cert_validation,
    }
    for field in ("ssh_password", "ssh_key_passphrase", "winrm_password"):
        EncryptMixin.decrypt_field(field, data)
    if target.ssh_key_file:
        try:
            with target.ssh_key_file.open("rb") as key_file:
                data["ssh_key_file"] = io.BytesIO(key_file.read())
        except Exception as exc:  # noqa: BLE001
            logger.info("读取目标 %s 的 SSH 私钥失败: %s", target.pk, exc)
            data["ssh_key_file"] = None
    return data


def probe_target_data(data: dict) -> TargetProbeResult:
    """沿与补丁执行一致的路由探测目标；表单数据中的凭据必须是明文。"""
    route: Optional[TargetExecutionRoute] = None
    try:
        route = resolve_target_execution_route(data)
        if route.transport == TargetTransport.NODE_EXECUTOR:
            return _probe_node_executor(data, route)
        if route.transport == TargetTransport.NATS_SSH:
            return _probe_nats_ssh(data, route)
        if route.transport == TargetTransport.ANSIBLE_WINRM:
            return _probe_ansible_winrm(data, route)
        raise ValueError(f"不支持的目标执行链路: {route.transport!r}")
    except Exception as exc:  # noqa: BLE001
        result = _failure_result(exc, route)
        logger.info(
            "目标连通性探测失败: ip=%s transport=%s reason=%s detail=%s",
            data.get("ip"),
            result.transport,
            result.reason_code,
            result.detail,
        )
        return result


def _probe_node_executor(data: dict, route: TargetExecutionRoute) -> TargetProbeResult:
    is_windows = data.get("os_type") == OSType.WINDOWS
    command = f"Write-Output {PROBE_MARKER}" if is_windows else f"printf {PROBE_MARKER}"
    result = Executor(route.instance_id).execute_local(
        command,
        timeout=PROBE_TIMEOUT,
        shell="powershell" if is_windows else "sh",
    )
    return _command_result(result, route, "节点 Executor 已在目标机成功执行探测命令")


def _probe_nats_ssh(data: dict, route: TargetExecutionRoute) -> TargetProbeResult:
    result = Executor(route.instance_id).execute_ssh(
        f"printf {PROBE_MARKER}",
        host=data["ip"],
        username=data.get("ssh_user") or "",
        password=data.get("ssh_password") or None,
        private_key=_read_private_key(data.get("ssh_key_file")),
        passphrase=data.get("ssh_key_passphrase") or None,
        port=route.port or 22,
        timeout=PROBE_TIMEOUT,
        connection_test=True,
        fast_fail=True,
    )
    return _command_result(result, route, "区域 NATS Executor 已通过 SSH 执行探测命令")


def _probe_ansible_winrm(data: dict, route: TargetExecutionRoute) -> TargetProbeResult:
    credential = {
        "host": data["ip"],
        "port": route.port or 5986,
        "user": data.get("winrm_user") or "",
        "password": data.get("winrm_password") or "",
        "connection": "winrm",
        "winrm_scheme": data.get("winrm_scheme") or "https",
        "winrm_transport": data.get("winrm_transport") or "ntlm",
        "winrm_cert_validation": data.get("winrm_cert_validation", True),
    }
    task_id = f"patch-target-connectivity-{uuid.uuid4().hex}"
    executor = AnsibleExecutor(route.instance_id)
    accepted = executor.adhoc(
        host_credentials=[credential],
        module="ansible.windows.win_ping",
        task_id=task_id,
        timeout=ANSIBLE_PROBE_TIMEOUT,
    )
    accepted_task_id = (
        accepted.get("task_id") if isinstance(accepted, dict) else None
    ) or task_id
    deadline = time.monotonic() + ANSIBLE_PROBE_TIMEOUT
    while time.monotonic() < deadline:
        query = executor.task_query(accepted_task_id, timeout=5)
        if not isinstance(query, dict):
            raise RuntimeError("Ansible Executor 返回格式异常")
        status = query.get("status")
        if status == "success":
            return TargetProbeResult(
                True,
                route.port,
                "区域 Ansible Executor 已通过 WinRM 完成 win_ping",
                route.transport,
            )
        if status in {"failed", "callback_failed"}:
            detail = query.get("message") or query.get("error") or status
            raise RuntimeError(f"WinRM win_ping 执行失败: {detail}")
        time.sleep(ANSIBLE_QUERY_INTERVAL)
    raise TimeoutError("WinRM win_ping 执行超时")


def _command_result(
    result: Any,
    route: TargetExecutionRoute,
    success_detail: str,
) -> TargetProbeResult:
    normalized = _normalize_result(result)
    exit_code = normalized.get("exit_code")
    if normalized.get("error"):
        raise RuntimeError(str(normalized["error"]))
    if normalized.get("success") is False:
        raise RuntimeError(
            str(normalized.get("message") or normalized.get("stderr") or "探测命令执行失败")
        )
    if exit_code is not None and int(exit_code) != 0:
        raise RuntimeError(
            f"探测命令退出码 {exit_code}: {normalized.get('stderr') or ''}"
        )
    if PROBE_MARKER not in str(normalized.get("stdout") or ""):
        return TargetProbeResult(
            False,
            route.port,
            "探测命令未返回预期标识",
            route.transport,
            "command",
            "command_failed",
        )
    return TargetProbeResult(True, route.port, success_detail, route.transport)


def _normalize_result(result: Any) -> dict:
    if isinstance(result, dict):
        nested = result.get("result")
        if isinstance(nested, dict):
            return {**result, **nested}
        if isinstance(nested, str) and not result.get("stdout"):
            return {**result, "stdout": nested}
        return result
    return {"exit_code": 0, "stdout": str(result) if result is not None else ""}


def _read_private_key(key_file) -> Optional[str]:
    if not key_file:
        return None
    if hasattr(key_file, "seek"):
        key_file.seek(0)
    raw = key_file.read() if hasattr(key_file, "read") else key_file
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


def _failure_result(
    exc: Exception,
    route: Optional[TargetExecutionRoute],
) -> TargetProbeResult:
    detail = _SECRET_RE.sub(r"\1***", str(exc) or exc.__class__.__name__)[:500]
    if isinstance(exc, ValueError):
        reason_code = "invalid_configuration"
        stage = "routing"
    elif isinstance(exc, TargetExecutorUnavailable):
        reason_code = "executor_unavailable"
        stage = "routing"
    elif isinstance(exc, TimeoutError) or "timeout" in detail.lower():
        reason_code = "connection_timeout"
        stage = "command"
    elif any(word in detail.lower() for word in ("auth", "password", "permission denied", "unauthorized")):
        reason_code = "authentication_failed"
        stage = "authentication"
    elif route is None:
        reason_code = "executor_unavailable"
        stage = "routing"
    else:
        reason_code = "command_failed"
        stage = "command"
    transport = route.transport if route else "unknown"
    return TargetProbeResult(False, route.port if route else None, detail, transport, stage, reason_code)
