# -*- coding: utf-8 -*-
"""PC 发现连接测试（Server 侧）。

未落库表单 payload 经 STARGAZER_URL 的 HTTP debug 端点直连 Stargazer，
复用真实 WinRM/SSH 链路做最小只读身份验证：不新增 NATS subject、
不创建 CollectModels、不写图实例、不执行软件扫描。

秘密只在转发 body 的内存中传递；对外错误只给稳定错误码与固定中文文案，
不透传 Stargazer 原始细节（可能夹带敏感信息）。
"""

import requests

from apps.cmdb.constants.constants import STARGAZER_URL
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger


class PCConnectionTestService:
    TIMEOUT_SECONDS = 15
    SUPPORTED_OS_TYPES = frozenset({"windows", "macos"})
    SECRET_FIELDS = ("password", "private_key", "passphrase")

    # 稳定错误码 → 固定中文文案
    ERROR_MESSAGES = {
        "TARGET_UNREACHABLE": "目标不可达，请检查网络连通性与端口配置",
        "WINRM_AUTH_FAILED": "WinRM 认证失败，请检查用户名与密码",
        "WINRM_TLS_FAILED": "WinRM TLS/证书校验失败，请检查 HTTPS 与证书配置",
        "SSH_AUTH_FAILED": "SSH 认证失败，请检查用户名、密码或私钥",
        "SSH_KEY_INVALID": "SSH 私钥或密码短语无效",
        "SCRIPT_TIMEOUT": "连接测试超时（15 秒），请检查目标负载与网络",
        "PC_IDENTITY_INVALID": "无法确认设备身份：硬件 UUID 与序列号均无效",
        "SCRIPT_OUTPUT_INVALID": "目标返回了无法识别的结果",
    }

    @classmethod
    def test_connection(cls, payload: dict) -> dict:
        payload = payload or {}
        os_type = payload.get("os_type", "")
        if os_type not in cls.SUPPORTED_OS_TYPES:
            raise BaseAppException("仅支持 windows 或 macos 的 PC 连接测试")
        host = str(payload.get("host") or "").strip()
        if not host:
            raise BaseAppException("测试主机不能为空")
        credential = payload.get("credential") or {}

        forward = {
            "os_type": os_type,
            "host": host,
            "node_id": payload.get("access_point_id") or payload.get("node_id") or "",
            "username": credential.get("username", ""),
            "port": int(credential.get("port") or (5986 if os_type == "windows" else 22)),
        }
        for field in cls.SECRET_FIELDS:
            if credential.get(field):
                forward[field] = credential[field]
        if os_type == "windows":
            forward["winrm_scheme"] = payload.get("winrm_scheme") or "https"
            forward["winrm_transport"] = payload.get("winrm_transport") or "ntlm"
            forward["winrm_cert_validation"] = bool(payload.get("winrm_cert_validation", False))

        url = f"{STARGAZER_URL.rstrip('/')}/api/collect/pc_test_connection"
        logger.info(
            "[PCConnectionTest] 开始连接测试 os_type=%s host=%s node_id=%s",
            os_type, host, forward["node_id"],
        )
        try:
            resp = requests.post(url, json=forward, timeout=cls.TIMEOUT_SECONDS)
            raw = resp.json()
        except requests.Timeout:
            logger.warning("[PCConnectionTest] Stargazer 连接测试超时 host=%s", host)
            return cls._error_result("SCRIPT_TIMEOUT")
        except requests.RequestException as exc:
            logger.error("[PCConnectionTest] 调用 Stargazer 失败: %s", type(exc).__name__)
            return cls._error_result("TARGET_UNREACHABLE")
        except ValueError:
            logger.error("[PCConnectionTest] Stargazer 返回非 JSON 响应 host=%s", host)
            return cls._error_result("SCRIPT_OUTPUT_INVALID")

        if not isinstance(raw, dict):
            return cls._error_result("SCRIPT_OUTPUT_INVALID")
        if raw.get("success"):
            return {
                "success": True,
                "os_type": raw.get("os_type") or os_type,
                "inst_name": raw.get("inst_name", ""),
                "hardware_uuid": raw.get("hardware_uuid", ""),
                "serial_number": raw.get("serial_number", ""),
                "error_code": "",
                "message": "",
            }
        error_code = raw.get("error_code")
        if error_code not in cls.ERROR_MESSAGES:
            error_code = "SCRIPT_OUTPUT_INVALID"
        return cls._error_result(error_code)

    @classmethod
    def _error_result(cls, error_code) -> dict:
        return {
            "success": False,
            "os_type": "",
            "inst_name": "",
            "hardware_uuid": "",
            "serial_number": "",
            "error_code": error_code,
            "message": cls.ERROR_MESSAGES[error_code],
        }
