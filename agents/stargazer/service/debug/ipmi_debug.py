# -- coding: utf-8 --
# @File: ipmi_debug.py
# @Time: 2026/05/08
"""
IPMI 协议诊断执行逻辑。
支持两类操作：
  - test_connection: 建立 IPMI 会话后执行轻量查询验证连通性与凭据
  - ipmi_collect: 获取 inventory 原始数据并格式化为可读文本
"""

import asyncio
import time

PRIVILEGE_MAP = {
    "callback": 1,
    "user": 2,
    "operator": 3,
    "administrator": 4,
}


def _resolve_privilege(credential: dict) -> int:
    privilege = str(credential.get("privilege", "administrator")).lower()
    return PRIVILEGE_MAP.get(privilege, PRIVILEGE_MAP["administrator"])


def _format_inventory(inventory: dict) -> str:
    """将 pyghmi get_inventory() 返回的 dict 格式化为可读文本。"""
    lines = []
    for section, data in inventory.items():
        lines.append(f"{section}:")
        if isinstance(data, dict):
            for k, v in data.items():
                lines.append(f"  {k}: {v}")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    lines.append(f"  [{i}]:")
                    for k, v in item.items():
                        lines.append(f"    {k}: {v}")
                else:
                    lines.append(f"  [{i}]: {item}")
        else:
            lines.append(f"  {data}")
    return "\n".join(lines)


def _classify_ipmi_error(e: Exception) -> tuple:
    """将 pyghmi 异常映射到 (stage, summary)。"""
    err_str = str(e).lower()
    if "timeout" in err_str or "timed out" in err_str:
        return "timeout", f"连接超时: {e}"
    if "authentication" in err_str or "credential" in err_str or "unauthorized" in err_str or "password" in err_str:
        return "auth", f"认证失败: {e}"
    if "connection refused" in err_str or "unreachable" in err_str or "no route" in err_str:
        return "connect", f"连接失败: {e}"
    return "unknown", f"未知错误: {e}"


def _run_ipmi_test_connection_sync(target: str, port: int, credential: dict) -> dict:
    """同步执行 IPMI 轻量连通性测试。"""
    start = time.time()
    try:
        from pyghmi.ipmi import command as ipmi_command

        username = credential.get("username", "")
        password = credential.get("password", "")
        kwargs = {
            "bmc": target,
            "userid": username,
            "password": password,
            "port": port,
            "privlevel": _resolve_privilege(credential),
        }

        ipmisession = ipmi_command.Command(**kwargs)
        # 轻量连通性查询
        power_state = ipmisession.get_power()
        duration_ms = int((time.time() - start) * 1000)

        raw_log = f"Power State: {power_state.get('powerstate', 'unknown')}"
        return {
            "success": True,
            "stage": None,
            "summary": None,
            "raw_log": raw_log,
            "duration_ms": duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        stage, summary = _classify_ipmi_error(e)
        return {
            "success": False,
            "stage": stage,
            "summary": summary,
            "raw_log": str(e),
            "duration_ms": duration_ms,
        }


def _run_ipmi_debug_sync(target: str, port: int, credential: dict) -> dict:
    """同步执行 IPMI inventory 采集。"""
    start = time.time()
    try:
        from pyghmi.ipmi import command as ipmi_command

        username = credential.get("username", "")
        password = credential.get("password", "")
        kwargs = {
            "bmc": target,
            "userid": username,
            "password": password,
            "port": port,
            "privlevel": _resolve_privilege(credential),
        }

        ipmisession = ipmi_command.Command(**kwargs)
        inventory = ipmisession.get_inventory()
        duration_ms = int((time.time() - start) * 1000)

        raw_log = _format_inventory(inventory) if isinstance(inventory, dict) else str(inventory)
        return {
            "success": True,
            "stage": None,
            "summary": None,
            "raw_log": raw_log,
            "duration_ms": duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        stage, summary = _classify_ipmi_error(e)
        return {
            "success": False,
            "stage": stage,
            "summary": summary,
            "raw_log": str(e),
            "duration_ms": duration_ms,
        }


async def run_ipmi_test_connection(params: dict) -> dict:
    """
    建立 IPMI 会话后执行轻量查询（get_power()）验证连通性与凭据。
    privilege 默认 administrator(4)，允许从 credential.privilege 读取。
    timeout: params["timeout"]（由 CMDB 注入，固定 10s）
    """
    target = params["target"]
    port = int(params.get("port", 623))
    timeout = int(params.get("timeout", 10))
    credential = params.get("credential", {})

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_ipmi_test_connection_sync, target, port, credential),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        result = {
            "success": False,
            "stage": "timeout",
            "summary": f"IPMI 连接超时: {target}:{port} 在 {timeout}s 内未响应",
            "raw_log": f"Timeout after {timeout}s",
            "duration_ms": timeout * 1000,
        }
    return result


async def run_ipmi_debug(params: dict) -> dict:
    """
    执行 IPMI 原始数据采集（get_inventory()）。
    privilege 默认 administrator(4)，允许从 credential.privilege 读取。
    timeout: params["timeout"]（由 CMDB 注入，固定 30s）
    """
    target = params["target"]
    port = int(params.get("port", 623))
    timeout = int(params.get("timeout", 30))
    credential = params.get("credential", {})

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_ipmi_debug_sync, target, port, credential),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        result = {
            "success": False,
            "stage": "timeout",
            "summary": f"IPMI 采集超时: {target}:{port} 在 {timeout}s 内未完成",
            "raw_log": f"Timeout after {timeout}s",
            "duration_ms": timeout * 1000,
        }
    return result
