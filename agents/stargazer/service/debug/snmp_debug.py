# -- coding: utf-8 --
# @File: snmp_debug.py
# @Time: 2026/05/08
"""
SNMP 协议诊断执行逻辑。
支持三类操作：
  - test_connection: 对固定 OID 1.3.6.1.2.1.1.1.0 执行轻量 snmpget
  - raw_collect: 从固定根 OID 1.3.6.1.2.1 执行 snmpbulkwalk
  - get_oid: 对用户指定 OID 执行 snmpbulkwalk
"""

import asyncio
import socket
import time

# Fixed OID for connectivity test
TEST_OID = "1.3.6.1.2.1.1.1.0"
# Fixed root OID for raw collection
RAW_COLLECT_OID = "1.3.6.1.2.1"


def _build_snmp_auth(credential: dict):
    """
    根据 SNMP version / level 构建 pysnmp CommunityData 或 UsmUserData。
    复用现有 SnmpFacts._get_snmp_auth() 逻辑。
    """
    from pysnmp.entity.rfc3413.oneliner import cmdgen
    from pysnmp.hlapi import usmAesCfb128Protocol, usmDESPrivProtocol, usmHMACMD5AuthProtocol, usmHMACSHAAuthProtocol

    version = credential.get("version", "v2c")
    if version in ("v2", "v2c"):
        return cmdgen.CommunityData(credential.get("community", "public"))

    # v3
    username = credential.get("username", "")
    authkey = credential.get("authkey", "")
    privkey = credential.get("privkey", "")
    integrity = credential.get("integrity", "sha")
    privacy = credential.get("privacy", "aes")
    level = credential.get("level", "authNoPriv")

    auth_proto = usmHMACSHAAuthProtocol if integrity == "sha" else usmHMACMD5AuthProtocol
    priv_proto = usmAesCfb128Protocol if privacy == "aes" else usmDESPrivProtocol

    if level == "authNoPriv":
        return cmdgen.UsmUserData(username, authKey=authkey, authProtocol=auth_proto)
    else:
        return cmdgen.UsmUserData(
            username,
            authKey=authkey,
            privKey=privkey,
            authProtocol=auth_proto,
            privProtocol=priv_proto,
        )


def _format_var_binds(var_binds) -> str:
    """将 pysnmp varBinds 格式化为 'OID = TYPE: VALUE' 文本。"""
    lines = []
    for oid, val in var_binds:
        oid_str = oid.prettyPrint()
        val_type = type(val).__name__
        val_str = val.prettyPrint()
        lines.append(f"{oid_str} = {val_type}: {val_str}")
    return "\n".join(lines)


def _classify_snmp_error(error_indication) -> tuple:
    """
    将 pysnmp errorIndication 映射到 (stage, summary)。
    """
    err_str = str(error_indication).lower()
    if "timeout" in err_str or "no response" in err_str:
        return "timeout", f"连接超时: {error_indication}"
    if "authentication" in err_str or "usm" in err_str or "password" in err_str:
        return "auth", f"认证失败: {error_indication}"
    if "connection refused" in err_str:
        return "connect", f"连接被拒绝: {error_indication}"
    return "unknown", f"未知错误: {error_indication}"


def _run_snmpget_sync(target: str, port: int, timeout: int, credential: dict, oid: str) -> dict:
    """同步执行 snmpget，返回标准结果 dict。"""
    from pysnmp.entity.rfc3413.oneliner import cmdgen

    start = time.time()
    try:
        auth = _build_snmp_auth(credential)
        cg = cmdgen.CommandGenerator()
        transport_opts = {"timeout": max(1, timeout - 1), "retries": 1}

        error_indication, error_status, error_index, var_binds = cg.getCmd(
            auth,
            cmdgen.UdpTransportTarget((target, port), **transport_opts),
            oid,
            lookupMib=False,
        )

        duration_ms = int((time.time() - start) * 1000)

        if error_indication:
            stage, summary = _classify_snmp_error(error_indication)
            return {
                "success": False,
                "stage": stage,
                "summary": summary,
                "raw_log": f"Error: {error_indication}",
                "duration_ms": duration_ms,
            }

        if error_status:
            summary = f"协议错误: {error_status.prettyPrint()} at {error_index}"
            return {
                "success": False,
                "stage": "collect",
                "summary": summary,
                "raw_log": summary,
                "duration_ms": duration_ms,
            }

        raw_log = _format_var_binds(var_binds)
        return {
            "success": True,
            "stage": None,
            "summary": None,
            "raw_log": raw_log,
            "duration_ms": duration_ms,
        }

    except socket.timeout:
        duration_ms = int((time.time() - start) * 1000)
        return {
            "success": False,
            "stage": "timeout",
            "summary": f"连接超时: {target}:{port} 无响应",
            "raw_log": f"Timeout connecting to {target}:{port}",
            "duration_ms": duration_ms,
        }
    except ConnectionRefusedError:
        duration_ms = int((time.time() - start) * 1000)
        return {
            "success": False,
            "stage": "connect",
            "summary": f"连接被拒绝: {target}:{port}",
            "raw_log": f"Connection refused: {target}:{port}",
            "duration_ms": duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        err_str = str(e).lower()
        if "authentication" in err_str or "usm" in err_str:
            stage, summary = "auth", f"认证失败: {e}"
        else:
            stage, summary = "unknown", f"未知错误: {e}"
        return {
            "success": False,
            "stage": stage,
            "summary": summary,
            "raw_log": str(e),
            "duration_ms": duration_ms,
        }


def _run_bulk_walk_sync(target: str, port: int, timeout: int, credential: dict, oid: str) -> dict:
    """同步执行 snmpbulkwalk，返回标准结果 dict。"""
    from pyasn1.type.univ import ObjectIdentifier
    from pysnmp.entity.rfc3413.oneliner import cmdgen
    from pysnmp.proto.rfc1905 import EndOfMibView

    start = time.time()
    try:
        auth = _build_snmp_auth(credential)
        cg = cmdgen.CommandGenerator()
        transport_opts = {"timeout": max(1, timeout - 2), "retries": 0}

        root_oid = ObjectIdentifier(oid)
        next_oid = oid
        last_seen_oid = None
        lines = []

        while True:
            error_indication, error_status, error_index, var_bind_table = cg.bulkCmd(
                auth,
                cmdgen.UdpTransportTarget((target, port), **transport_opts),
                0,
                25,  # nonRepeaters=0, maxRepetitions=25
                next_oid,
                lookupMib=False,
            )

            if error_indication:
                duration_ms = int((time.time() - start) * 1000)
                stage, summary = _classify_snmp_error(error_indication)
                return {
                    "success": False,
                    "stage": stage,
                    "summary": summary,
                    "raw_log": f"Error: {error_indication}",
                    "duration_ms": duration_ms,
                }

            if error_status:
                duration_ms = int((time.time() - start) * 1000)
                summary = f"协议错误: {error_status.prettyPrint()} at {error_index}"
                return {
                    "success": False,
                    "stage": "collect",
                    "summary": summary,
                    "raw_log": summary,
                    "duration_ms": duration_ms,
                }

            if not var_bind_table:
                break

            batch_last_oid = None
            walk_finished = False

            for var_binds in var_bind_table:
                for current_oid, val in var_binds:
                    if isinstance(val, EndOfMibView) or not root_oid.isPrefixOf(current_oid):
                        walk_finished = True
                        break

                    current_oid_str = current_oid.prettyPrint()
                    if current_oid_str == last_seen_oid:
                        walk_finished = True
                        break

                    val_type = type(val).__name__
                    val_str = val.prettyPrint()
                    lines.append(f"{current_oid_str} = {val_type}: {val_str}")
                    last_seen_oid = current_oid_str
                    batch_last_oid = current_oid_str

                if walk_finished:
                    break

            if walk_finished or not batch_last_oid:
                break

            next_oid = batch_last_oid

        duration_ms = int((time.time() - start) * 1000)

        if not lines:
            return {
                "success": False,
                "stage": "collect",
                "summary": "指定 OID 下无可遍历数据，可能是叶子节点或无权限访问",
                "raw_log": "No walkable data returned for the specified OID.",
                "duration_ms": duration_ms,
            }

        raw_log = "\n".join(lines)
        return {
            "success": True,
            "stage": None,
            "summary": None,
            "raw_log": raw_log,
            "duration_ms": duration_ms,
        }

    except socket.timeout:
        duration_ms = int((time.time() - start) * 1000)
        return {
            "success": False,
            "stage": "timeout",
            "summary": f"连接超时: {target}:{port} 无响应",
            "raw_log": f"Timeout connecting to {target}:{port}",
            "duration_ms": duration_ms,
        }
    except ConnectionRefusedError:
        duration_ms = int((time.time() - start) * 1000)
        return {
            "success": False,
            "stage": "connect",
            "summary": f"连接被拒绝: {target}:{port}",
            "raw_log": f"Connection refused: {target}:{port}",
            "duration_ms": duration_ms,
        }
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        err_str = str(e).lower()
        if "authentication" in err_str or "usm" in err_str:
            stage, summary = "auth", f"认证失败: {e}"
        else:
            stage, summary = "unknown", f"未知错误: {e}"
        return {
            "success": False,
            "stage": stage,
            "summary": summary,
            "raw_log": str(e),
            "duration_ms": duration_ms,
        }


async def run_snmp_test_connection(params: dict) -> dict:
    """
    对固定 OID 1.3.6.1.2.1.1.1.0 执行一次 snmpget。
    timeout: params["timeout"]（由 CMDB 注入，固定 10s）
    """
    target = params["target"]
    port = int(params.get("port", 161))
    timeout = int(params.get("timeout", 10))
    credential = params.get("credential", {})

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_snmpget_sync, target, port, timeout, credential, TEST_OID),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        result = {
            "success": False,
            "stage": "timeout",
            "summary": f"连接超时: {target}:{port} 无响应",
            "raw_log": f"Timeout after {timeout}s",
            "duration_ms": timeout * 1000,
        }
    return result


async def run_bulk_walk(params: dict) -> dict:
    """
    从固定根 OID 1.3.6.1.2.1 执行 snmpbulkwalk。
    timeout: params["timeout"]（由 CMDB 注入，固定 60s）
    """
    return await _run_bulk_walk(params, RAW_COLLECT_OID)


async def run_get_oid(params: dict) -> dict:
    """
    对 params["oid"] 执行 snmpbulkwalk。
    timeout: params["timeout"]（由 CMDB 注入，固定 60s）
    """
    oid = params.get("oid", "")

    if not oid:
        return {
            "success": False,
            "stage": "param",
            "summary": "OID 不能为空",
            "raw_log": "",
            "duration_ms": 0,
        }

    return await _run_bulk_walk(params, oid)


async def _run_bulk_walk(params: dict, oid: str) -> dict:
    target = params["target"]
    port = int(params.get("port", 161))
    timeout = int(params.get("timeout", 60))
    credential = params.get("credential", {})

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_bulk_walk_sync, target, port, timeout, credential, oid),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        result = {
            "success": False,
            "stage": "timeout",
            "summary": f"采集超时: {target}:{port} 在 {timeout}s 内未完成",
            "raw_log": f"Timeout after {timeout}s",
            "duration_ms": timeout * 1000,
        }
    return result
