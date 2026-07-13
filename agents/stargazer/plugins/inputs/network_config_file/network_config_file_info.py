import base64
import re
import time

try:
    from netmiko import ConnectHandler
except Exception:
    ConnectHandler = None

from plugins.inputs.network_config_file.constants import (
    COMMAND_ERROR_PATTERNS,
    DEVICE_TYPE_DISABLE_PAGING,
    DANGEROUS_COMMAND_PREFIXES,
    DANGEROUS_EXACT_COMMANDS,
    SUPPORTED_DEVICE_TYPES,
)


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
            raise ValueError(f"不支持的 Netmiko 驱动: {device_type}")
        return {
            "device_type": device_type,
            "ip": self.params.get("host") or self.params.get("connect_ip"),
            "username": self.params.get("username"),
            "password": self.params.get("password"),
            "secret": self.params.get("enable_password") or "",
            "port": int(self.params.get("port") or 22),
            "allow_agent": False,
            "use_keys": False,
            "conn_timeout": int(self.params.get("conn_timeout") or 30),
            "timeout": int(self.params.get("timeout") or 60),
        }

    def _success_payload(self, merged_output: str) -> dict:
        encoded = base64.b64encode(merged_output.encode()).decode()
        config_name = str(self.params.get("config_name") or "").strip()
        return {
            "collect_task_id": self.params.get("collect_task_id"),
            "instance_id": self.params.get("target_instance_id") or self.params.get("host") or "",
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

    def list_all_resources(self, need_raw=False):
        del need_raw
        command_results = []
        failures = []
        try:
            commands = self._commands()
            connect_params = self._connect_params()
            if ConnectHandler is None:
                raise RuntimeError("netmiko is required for network config file collection")

            with ConnectHandler(**connect_params) as net_connect:
                if self.params.get("enable_password"):
                    net_connect.enable()
                paging_command = DEVICE_TYPE_DISABLE_PAGING.get(connect_params["device_type"])
                if paging_command:
                    net_connect.disable_paging(command=paging_command)

                for command in commands:
                    started = time.monotonic()
                    try:
                        output = net_connect.send_command(command)
                        duration_ms = int((time.monotonic() - started) * 1000)
                        if self._has_command_error(output):
                            failures.append(f"{command}: {output[:200]}")
                            command_results.append(
                                {"command": command, "status": "error", "error": output[:200], "duration_ms": duration_ms}
                            )
                            continue
                        command_results.append(
                            {"command": command, "status": "success", "output": output, "duration_ms": duration_ms}
                        )
                    except Exception as err:
                        duration_ms = int((time.monotonic() - started) * 1000)
                        failures.append(f"{command}: {err}")
                        command_results.append(
                            {"command": command, "status": "error", "error": str(err), "duration_ms": duration_ms}
                        )

            if failures:
                return {"success": False, "result": {"cmdb_collect_error": "; ".join(failures)[:2000]}}
            return {"success": True, "result": self._success_payload(self.merge_command_outputs(command_results))}
        except Exception as err:
            return {"success": False, "result": {"cmdb_collect_error": str(err)[:2000]}}
