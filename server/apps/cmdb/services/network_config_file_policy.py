from __future__ import annotations

import re
from collections.abc import Iterable

from apps.core.exceptions.base_app_exception import BaseAppException

SUPPORTED_NETWORK_CONFIG_MODELS = {"switch", "router", "firewall", "loadbalance"}

BRAND_DEVICE_TYPE_ALIASES = {
    "华为": "huawei",
    "huawei": "huawei",
    "h3c": "hp_comware",
    "hp comware": "hp_comware",
    "hewlett-packard": "hp_comware",
    "hewlett packard": "hp_comware",
    "cisco": "cisco_ios",
    "juniper": "juniper_junos",
    "f5": "f5_tmsh",
    "fortinet": "fortinet",
}

SUPPORTED_BRAND_OPTIONS = [
    {"label": "华为 / Huawei", "device_type": "huawei"},
    {"label": "H3C / HP Comware", "device_type": "hp_comware"},
    {"label": "Cisco", "device_type": "cisco_ios"},
    {"label": "Juniper", "device_type": "juniper_junos"},
    {"label": "F5", "device_type": "f5_tmsh"},
    {"label": "Fortinet", "device_type": "fortinet"},
]

DANGEROUS_EXACT_COMMANDS = {"conf t", "write erase"}
# P1-2.5: 补全真实高危操作,覆盖:
# - 写配置: write memory (Cisco)
# - 系统请求: request system (Junos 重启/关机/备份)
# - 模式逃逸: do (Cisco 从 config 模式临时跑任意命令)
# - shell 逃逸: sudo / bash / sh / python / perl / ruby
# - 文件破坏: rm
# - 跳转/隧道: telnet / ssh
DANGEROUS_COMMAND_PREFIXES = {
    "configure",
    "reload",
    "reboot",
    "reset",
    "delete",
    "erase",
    "format",
    "copy",
    "scp",
    "tftp",
    "ftp",
    "install",
    "upgrade",
    "commit",
    "save",
    "shutdown",
    "undo",
    "set",
    "write",
    "request",
    "do",
    "sudo",
    "bash",
    "sh",
    "python",
    "perl",
    "ruby",
    "rm",
    "telnet",
    "ssh",
}
MAX_ERROR_SUMMARY_LENGTH = 2000


def normalize_brand(brand: str | None) -> str:
    return " ".join(str(brand or "").strip().lower().split())


def resolve_device_type(brand: str | None) -> str:
    normalized = normalize_brand(brand)
    if not normalized:
        raise BaseAppException("网络设备缺少厂商字段，无法匹配采集驱动")
    device_type = BRAND_DEVICE_TYPE_ALIASES.get(normalized)
    if not device_type:
        raise BaseAppException(f"当前厂商暂不支持网络配置采集: {brand}")
    return device_type


def get_supported_brand_options() -> list[dict]:
    return [dict(item) for item in SUPPORTED_BRAND_OPTIONS]


def split_commands(raw_commands: str | Iterable[str] | None) -> list[str]:
    if raw_commands is None:
        return []
    if isinstance(raw_commands, str):
        lines = raw_commands.splitlines()
    else:
        lines = list(raw_commands)
    return [str(line).strip() for line in lines if str(line).strip()]


def validate_safe_command(command: str) -> str:
    normalized = " ".join(str(command or "").strip().split())
    lowered = normalized.lower()
    if not lowered:
        raise BaseAppException("采集命令不能为空")
    if lowered in DANGEROUS_EXACT_COMMANDS:
        raise BaseAppException(f"采集命令存在高危操作: {normalized}")
    first_word = re.split(r"\s+", lowered, maxsplit=1)[0]
    if first_word in DANGEROUS_COMMAND_PREFIXES:
        raise BaseAppException(f"采集命令存在高危操作: {normalized}")
    return normalized


def validate_commands(raw_commands: str | Iterable[str] | None) -> list[str]:
    commands = split_commands(raw_commands)
    if not commands:
        raise BaseAppException("采集命令不能为空")
    return [validate_safe_command(command) for command in commands]


def truncate_error_summary(error: str) -> str:
    value = str(error or "")
    if len(value) <= MAX_ERROR_SUMMARY_LENGTH:
        return value
    return value[:MAX_ERROR_SUMMARY_LENGTH] + "...[truncated]"


def validate_network_config_instance(instance: dict) -> dict:
    model_id = str(instance.get("model_id") or "").strip()
    if model_id not in SUPPORTED_NETWORK_CONFIG_MODELS:
        raise BaseAppException("网络配置采集仅支持 switch/router/firewall/loadbalance")
    host = str(instance.get("ip_addr") or instance.get("host") or "").strip()
    if not host:
        raise BaseAppException("网络设备缺少管理IP")
    device_type = resolve_device_type(instance.get("brand"))
    return {**instance, "host": host, "device_type": device_type}
