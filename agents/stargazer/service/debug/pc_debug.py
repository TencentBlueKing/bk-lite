# -*- coding: utf-8 -*-
"""PC 发现连接测试：真实链路的最小只读身份验证。

复用 PCInventoryCollector 的连接构造（ansible_adhoc/winrm、SSHPlugin）与身份规范化，
但固定使用随插件发布的最小身份脚本：只验证网络与认证、读取硬件 UUID/序列号与系统版本，
绝不执行软件扫描，也不写 CMDB。

企业版采集器按需惰性导入：开源部署缺少 enterprise 包时返回稳定错误码，
不阻断 Stargazer 启动与其他协议诊断。
"""

from sanic.log import logger

PC_CONNECTION_TEST_TIMEOUT = 15

IDENTITY_SCRIPTS = {
    "windows": "enterprise/plugins/inputs/pc/pc_windows_identity.ps1",
    "macos": "enterprise/plugins/inputs/pc/pc_macos_identity.sh",
}

_FALLBACK_ERROR_CODE = "SCRIPT_OUTPUT_INVALID"


def _error(error_code, message=""):
    return {
        "success": False,
        "os_type": "",
        "inst_name": "",
        "hardware_uuid": "",
        "serial_number": "",
        "error_code": error_code,
        "message": message,
    }


def _parse_collect_error(raw_result, pc_error_codes):
    """把采集器 cmdb_collect_error 收敛到稳定错误码；非合同码一律兜底，不透传原文。"""
    text = str((raw_result or {}).get("cmdb_collect_error") or "")
    code, _, _message = text.partition(":")
    code = code.strip()
    if code not in pc_error_codes:
        return _FALLBACK_ERROR_CODE
    return code


async def run_pc_test_connection(params: dict) -> dict:
    """执行最小连接测试，返回 {success, os_type, inst_name, hardware_uuid, serial_number, error_code, message}。"""
    params = params or {}
    os_type = params.get("os_type", "")
    if os_type not in IDENTITY_SCRIPTS:
        return _error(_FALLBACK_ERROR_CODE, f"unsupported os_type: {os_type}")
    if not params.get("host"):
        return _error(_FALLBACK_ERROR_CODE, "host is required")

    try:
        from enterprise.plugins.inputs.pc.pc_inventory import PC_ERROR_CODES, PCInventoryCollector
    except ImportError:
        logger.error("[pc_debug] enterprise PC plugin unavailable")
        return _error(_FALLBACK_ERROR_CODE, "pc enterprise plugin unavailable")

    collector_params = dict(params)
    collector_params["script_path"] = IDENTITY_SCRIPTS[os_type]
    collector_params["execute_timeout"] = PC_CONNECTION_TEST_TIMEOUT
    # 连接测试只读身份，禁止携带任何回传参数
    collector_params.pop("callback_subject", None)

    logger.info(
        "[pc_debug] test connection os_type=%s host=%s", os_type, params.get("host")
    )

    raw = await PCInventoryCollector(collector_params).list_all_resources()
    if not raw.get("success"):
        return _error(_parse_collect_error(raw.get("result"), PC_ERROR_CODES))

    pc_rows = (raw.get("result") or {}).get("pc") or []
    if not pc_rows:
        return _error("PC_IDENTITY_INVALID")
    pc_row = pc_rows[0]
    return {
        "success": True,
        "os_type": os_type,
        "inst_name": pc_row.get("inst_name", ""),
        "hardware_uuid": pc_row.get("hardware_uuid", ""),
        "serial_number": pc_row.get("serial_number", ""),
        "error_code": "",
        "message": "",
    }
