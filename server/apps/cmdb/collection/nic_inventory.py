# -*- coding: utf-8 -*-
"""物理服务器 SSH 采集的网卡入库规则（Step-1）。

稳定身份是规范化后的 MAC；loopback 与空/非法 MAC 不入库。
"""
import re

_HEX_MAC_RE = re.compile(r"^[0-9a-f]{12}$")
_EMPTY_MACS = frozenset({"000000000000"})
_EMPTY_MAC_TOKENS = frozenset({"", "n/a", "na", "none", "null", "unknown", "-"})


def normalize_nic_mac(raw) -> str:
    """把 MAC 规范成小写冒号分隔（aa:bb:cc:dd:ee:ff）；非法或空值返回空串。"""
    if raw is None:
        return ""
    token = str(raw).strip().lower()
    if token in _EMPTY_MAC_TOKENS:
        return ""
    hex_only = re.sub(r"[^0-9a-f]", "", token)
    if hex_only in _EMPTY_MACS or not _HEX_MAC_RE.fullmatch(hex_only):
        return ""
    return ":".join(hex_only[index : index + 2] for index in range(0, 12, 2))


def is_loopback_iface(iface) -> bool:
    name = str(iface or "").strip().lower()
    return name == "lo" or name.startswith("lo:")


def is_ingestible_nic(iface, mac) -> bool:
    if is_loopback_iface(iface):
        return False
    return bool(normalize_nic_mac(mac))


def parse_nic_record(raw) -> dict | None:
    """解析单条网卡：丢掉 lo / 空 MAC，并用规范化 MAC 作为 inst_name。"""
    if not isinstance(raw, dict):
        return None
    iface = str(raw.get("nic_iface") or "").strip()
    mac = normalize_nic_mac(raw.get("nic_mac"))
    if not is_ingestible_nic(iface, mac):
        return None
    parsed = dict(raw)
    parsed["nic_iface"] = iface
    parsed["nic_mac"] = mac
    parsed["inst_name"] = mac
    return parsed
