import base64
import re
import time
import uuid

from core.logger import logger
from plugins.inputs.network_config_file.constants import (
    COMMAND_ERROR_PATTERNS,
    DANGEROUS_COMMAND_PREFIXES,
    DANGEROUS_EXACT_COMMANDS,
    DEVICE_TYPE_DISABLE_PAGING,
    SCRAPLI_PLATFORM_BY_DEVICE_TYPE,
    SUPPORTED_DEVICE_TYPES,
)
from scrapli import AsyncScrapli
from scrapli.driver.generic.async_driver import AsyncGenericDriver


def validate_safe_command(command: str) -> str:
    normalized = " ".join(str(command or "").strip().split())
    lowered = normalized.lower()
    if not lowered:
        raise ValueError("采集命令不能为空")
    if lowered in DANGEROUS_EXACT_COMMANDS:
        raise ValueError(f"采集命令存在高危操作: {normalized}")
    first_word = re.split(r"\s+", lowered, maxsplit=1)[0]
    if first_word in DANGEROUS_COMMAND_PREFIXES:
        raise ValueError(f"采集命令存在高危操作: {normalized}")
    return normalized


class NetworkConfigFileInfo:
    def __init__(self, params):
        self.params = params or {}

    @staticmethod
    def merge_command_outputs(results: list[dict]) -> str:
        sections = []
        for item in results:
            sections.append(f"===== command: {item.get('command', '')} =====\n{item.get('output', '')}")
        return "\n\n".join(sections)

    @staticmethod
    def _has_command_error(output: str) -> bool:
        lowered = str(output or "").lower()
        return any(pattern in lowered for pattern in COMMAND_ERROR_PATTERNS)

    def _commands(self) -> list[str]:
        return [validate_safe_command(line) for line in str(self.params.get("commands") or "").splitlines() if line.strip()]

    def _connect_params(self) -> dict:
        device_type = str(self.params.get("device_type") or "").strip()
        if device_type not in SUPPORTED_DEVICE_TYPES:
            raise ValueError(f"不支持的异步网络驱动: {device_type}")
        return {
            "platform": SCRAPLI_PLATFORM_BY_DEVICE_TYPE[device_type],
            "host": self.params.get("host") or self.params.get("connect_ip"),
            "auth_username": self.params.get("username"),
            "auth_password": self.params.get("password"),
            "auth_secondary": self.params.get("enable_password") or "",
            "port": int(self.params.get("port") or 22),
            "auth_strict_key": True,
            "transport": "asyncssh",
            "timeout_socket": 30.0,  # 建连超时硬编码
            "timeout_transport": 30.0,
            "timeout_ops": 60.0,  # 单命令超时硬编码；表单 timeout 由框架作单对象预算
        }

    @staticmethod
    def _create_connection(connect_params: dict):
        if connect_params["platform"] != "f5_tmsh":
            return AsyncScrapli(**connect_params)
        generic_params = dict(connect_params)
        generic_params.pop("platform", None)
        generic_params.pop("auth_secondary", None)
        return AsyncGenericDriver(**generic_params)

    def _success_payload(self, merged_output: str) -> dict:
        if str(self.params.get("protocol_version") or "") != "2":
            raise ValueError("unsupported config collection protocol version")
        target_instance_uuid = str(self.params.get("target_instance_uuid") or "").strip()
        try:
            parsed_uuid = uuid.UUID(target_instance_uuid)
        except (TypeError, ValueError, AttributeError) as err:
            raise ValueError("target_instance_uuid must be a valid UUIDv4") from err
        if parsed_uuid.version != 4 or str(parsed_uuid) != target_instance_uuid.lower():
            raise ValueError("target_instance_uuid must be a canonical UUIDv4")

        encoded = base64.b64encode(merged_output.encode()).decode()
        config_name = str(self.params.get("config_name") or "").strip()
        return {
            "collect_task_id": self.params.get("collect_task_id"),
            "protocol_version": "2",
            "instance_uuid": target_instance_uuid,
            "instance_name": self.params.get("instance_name") or self.params.get("host") or "",
            "model_id": self.params.get("target_model_id"),
            "file_path": f"network://{config_name}",
            "file_name": config_name,
            "version": str(int(time.time() * 1000)),
            "status": "success",
            "size": len(merged_output.encode()),
            "error": "",
            "content_base64": encoded,
        }

    async def list_all_resources(self, need_raw=False):
        del need_raw
        command_results = []
        failures = []
        connection = None
        try:
            commands = self._commands()
            connect_params = self._connect_params()
            connection = self._create_connection(connect_params)
            await connection.open()
            if self.params.get("enable_password"):
                await connection.acquire_priv("privilege_exec")
            device_type = str(self.params.get("device_type") or "")
            paging_command = DEVICE_TYPE_DISABLE_PAGING.get(device_type)
            if paging_command:
                await connection.send_command(paging_command)

            for command in commands:
                started = time.monotonic()
                try:
                    response = await connection.send_command(command)
                    output = str(response.result or "")
                    duration_ms = int((time.monotonic() - started) * 1000)
                    if bool(response.failed) or self._has_command_error(output):
                        failures.append(f"{command}: {output[:200]}")
                        command_results.append(
                            {
                                "command": command,
                                "status": "error",
                                "error": output[:200],
                                "duration_ms": duration_ms,
                            }
                        )
                        continue
                    command_results.append(
                        {
                            "command": command,
                            "status": "success",
                            "output": output,
                            "duration_ms": duration_ms,
                        }
                    )
                except Exception as err:
                    duration_ms = int((time.monotonic() - started) * 1000)
                    failures.append(f"{command}: {type(err).__name__}")
                    command_results.append(
                        {
                            "command": command,
                            "status": "error",
                            "error": type(err).__name__,
                            "duration_ms": duration_ms,
                        }
                    )

            if failures:
                return {
                    "success": False,
                    "result": {"cmdb_collect_error": "; ".join(failures)[:2000]},
                }
            return {
                "success": True,
                "result": self._success_payload(self.merge_command_outputs(command_results)),
            }
        except Exception as err:
            return {
                "success": False,
                "result": {"cmdb_collect_error": type(err).__name__},
            }
        finally:
            if connection is not None:
                try:
                    await connection.close()
                except Exception as close_error:  # 关闭失败不得覆盖主采集结果
                    logger.warning(
                        "event=network_config_close_failed target=%s error_type=%s",
                        self.params.get("host") or self.params.get("connect_ip") or "-",
                        type(close_error).__name__,
                    )
