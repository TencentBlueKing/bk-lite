# -*- coding: utf-8 -*-
"""物理服务器 SSH 脚本输出解析（无 Sanic / SSH 依赖，便于单测）。"""
import re
from typing import Any, Dict, Optional

_EMPTY_MAC_TOKENS = frozenset({"", "n/a", "na", "none", "null", "unknown", "-"})


def normalize_nic_mac(raw) -> str:
    """把 MAC 规范成小写冒号分隔；非法或空值返回空串。"""
    if raw is None:
        return ""
    token = str(raw).strip().lower()
    if token in _EMPTY_MAC_TOKENS:
        return ""
    hex_only = re.sub(r"[^0-9a-f]", "", token)
    if hex_only == "000000000000" or not re.fullmatch(r"[0-9a-f]{12}", hex_only):
        return ""
    return ":".join(hex_only[index : index + 2] for index in range(0, 12, 2))


def parse_server_info(shell_output: str) -> Dict[str, Any]:
    """
    解析物理服务器shell输出为JSON格式

    基于 === section === 标记来识别不同类型的数据
    """
    result: Dict[str, Any] = {
        "disk": [],
        "memory": [],
        "nic": [],
        "gpu": [],
    }

    lines = shell_output.strip().split("\n")
    current_section = None
    current_item: Dict[str, Any] = {}

    list_sections = {
        "disk_info": "disk",
        "mem_info": "memory",
        "NIC info": "nic",
        "GPU info": "gpu",
    }

    for line in lines:
        line = line.strip()
        if not line or line.startswith("【") or line.startswith("---"):
            continue

        if line.startswith("===") and line.endswith("==="):
            if current_section and current_item:
                if current_section in list_sections:
                    _append_list_section_item(result, current_section, current_item, list_sections)
                current_item = {}

            section_match = re.search(r"===\s*(.+?)\s*===", line)
            if section_match:
                current_section = section_match.group(1).strip()
            continue

        if "=" in line and current_section:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if current_section in list_sections:
                if current_item and is_new_item_start(key, current_section):
                    _append_list_section_item(result, current_section, current_item, list_sections)
                    current_item = {}
                current_item[key] = value
            else:
                result[key] = value

    if current_section and current_item:
        if current_section in list_sections:
            _append_list_section_item(result, current_section, current_item, list_sections)

    return result


def _prepare_nic_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    iface = str(item.get("nic_iface") or "").strip()
    name = iface.lower()
    if name == "lo" or name.startswith("lo:"):
        return None
    mac = normalize_nic_mac(item.get("nic_mac"))
    if not mac:
        return None
    prepared = dict(item)
    prepared["nic_iface"] = iface
    prepared["nic_mac"] = mac
    return prepared


def _append_list_section_item(result, current_section, current_item, list_sections):
    item = current_item
    if list_sections[current_section] == "nic":
        item = _prepare_nic_item(current_item)
        if item is None:
            return
    result[list_sections[current_section]].append(item)


def is_new_item_start(key: str, section: str) -> bool:
    start_keys = {
        "disk_info": "disk_name",
        "mem_info": "mem_locator",
        "NIC info": "nic_pci_addr",
        "GPU info": "gpu_name",
    }
    return key == start_keys.get(section)
