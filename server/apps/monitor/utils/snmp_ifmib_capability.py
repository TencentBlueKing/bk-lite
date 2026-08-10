"""公共 IF-MIB 能力与指标来源的唯一判定入口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.db import DatabaseError

from apps.core.logger import monitor_logger as logger

NETWORK_DEVICE_TYPE_ID = "Network Device"
CORE_IFMIB_OBJECT_NAMES = frozenset({"Switch", "Router", "Firewall", "Loadbalance"})
IFMIB_METRIC_CATALOG = (
    (
        "Status",
        "interface_ifAdminStatus",
        "Interface Admin Status",
        "Enum",
        '[{"name":"up","id":1,"color":"#1ac44a"},{"name":"down","id":2,"color":"#ff4d4f"},{"name":"testing","id":3,"color":"#faad14"}]',
        "Interface administrative status.",
    ),
    (
        "Status",
        "interface_ifOperStatus",
        "Interface Oper Status",
        "Enum",
        '[{"name":"up","id":1,"color":"#1ac44a"},{"name":"down","id":2,"color":"#ff4d4f"},'
        '{"name":"testing","id":3,"color":"#faad14"},{"name":"unknown","id":4,"color":"#8c8c8c"},'
        '{"name":"dormant","id":5,"color":"#faad14"},{"name":"notPresent","id":6,"color":"#8c8c8c"},'
        '{"name":"lowerLayerDown","id":7,"color":"#ff4d4f"}]',
        "Actual interface operational status.",
    ),
    ("Bandwidth", "interface_ifSpeed", "Interface Bandwidth", "Number", "bitps", "Maximum supported interface speed."),
    ("Packet Error", "interface_ifInErrors", "Incoming Errors Rate", "Number", "cps", "Average inbound error packets per second over five minutes."),
    (
        "Packet Error",
        "interface_ifOutErrors",
        "Outgoing Errors Rate",
        "Number",
        "cps",
        "Average outbound error packets per second over five minutes.",
    ),
    (
        "Packet Loss",
        "interface_ifInDiscards",
        "Incoming Discards Rate",
        "Number",
        "cps",
        "Average inbound discarded packets per second over five minutes.",
    ),
    (
        "Packet Loss",
        "interface_ifOutDiscards",
        "Outgoing Discards Rate",
        "Number",
        "cps",
        "Average outbound discarded packets per second over five minutes.",
    ),
    (
        "Packet",
        "interface_ifInUcastPkts",
        "Incoming Unicast Packets Rate",
        "Number",
        "cps",
        "Average inbound unicast packets per second over five minutes.",
    ),
    (
        "Packet",
        "interface_ifOutUcastPkts",
        "Outgoing Unicast Packets Rate",
        "Number",
        "cps",
        "Average outbound unicast packets per second over five minutes.",
    ),
    (
        "Traffic",
        "interface_ifInOctets",
        "Interface Incoming Traffic Rate",
        "Number",
        "byteps",
        "Average inbound interface bytes per second over five minutes.",
    ),
    (
        "Traffic",
        "interface_ifOutOctets",
        "Interface Outgoing Traffic Rate",
        "Number",
        "byteps",
        "Average outbound interface bytes per second over five minutes.",
    ),
    (
        "Traffic",
        "interface_ifHCInOctets",
        "Interface Incoming Traffic Rate (HC)",
        "Number",
        "byteps",
        "Average inbound 64-bit interface bytes per second over five minutes.",
    ),
    (
        "Traffic",
        "interface_ifHCOutOctets",
        "Interface Outgoing Traffic Rate (HC)",
        "Number",
        "byteps",
        "Average outbound 64-bit interface bytes per second over five minutes.",
    ),
    (
        "Traffic",
        "device_total_incoming_traffic",
        "Device Total Incoming Traffic Rate",
        "Number",
        "byteps",
        "Total inbound interface bytes per second over five minutes.",
    ),
    (
        "Traffic",
        "device_total_outgoing_traffic",
        "Device Total Outgoing Traffic Rate",
        "Number",
        "byteps",
        "Total outbound interface bytes per second over five minutes.",
    ),
)
COMMON_IFMIB_METRIC_NAMES = frozenset(metric[1] for metric in IFMIB_METRIC_CATALOG)

# 公共 IF-MIB 指标在中文控制台的唯一展示目录。采集器字段名保持 RFC/Prometheus
# 命名，页面只通过此目录取得中文名称和说明。
IFMIB_ZH_DISPLAY_TEXTS = {
    "interface_ifAdminStatus": ("接口管理状态", "接口在设备配置中的启用或关闭状态。"),
    "interface_ifOperStatus": ("接口运行状态", "接口当前实际运行状态。"),
    "interface_ifSpeed": ("接口带宽", "接口支持的最大速率。"),
    "interface_ifInErrors": ("接口接收错包速率", "按最近 5 分钟计算的每秒平均接收错误报文数。"),
    "interface_ifOutErrors": ("接口发送错包速率", "按最近 5 分钟计算的每秒平均发送错误报文数。"),
    "interface_ifInDiscards": ("接口接收丢弃包速率", "按最近 5 分钟计算的每秒平均接收丢弃报文数。"),
    "interface_ifOutDiscards": ("接口发送丢弃包速率", "按最近 5 分钟计算的每秒平均发送丢弃报文数。"),
    "interface_ifInUcastPkts": ("接口接收单播包速率", "按最近 5 分钟计算的每秒平均接收单播报文数。"),
    "interface_ifOutUcastPkts": ("接口发送单播包速率", "按最近 5 分钟计算的每秒平均发送单播报文数。"),
    "interface_ifInOctets": ("接口接收流量速率（32 位）", "按最近 5 分钟计算的每秒平均接收字节数。"),
    "interface_ifOutOctets": ("接口发送流量速率（32 位）", "按最近 5 分钟计算的每秒平均发送字节数。"),
    "interface_ifHCInOctets": ("接口接收流量速率（64 位）", "按最近 5 分钟计算的每秒平均接收字节数。"),
    "interface_ifHCOutOctets": ("接口发送流量速率（64 位）", "按最近 5 分钟计算的每秒平均发送字节数。"),
    "device_total_incoming_traffic": ("设备接收总流量速率", "按最近 5 分钟计算的所有接口每秒平均接收字节数。"),
    "device_total_outgoing_traffic": ("设备发送总流量速率", "按最近 5 分钟计算的所有接口每秒平均发送字节数。"),
}


def get_ifmib_metric_names_matching_keyword(keyword: str, locale: str) -> set[str]:
    """Return metric IDs whose localized public catalog text contains ``keyword``."""
    normalized_keyword = str(keyword or "").strip().casefold()
    if not normalized_keyword or not str(locale or "").startswith("zh"):
        return set()
    return {
        metric_name
        for metric_name, display_text in IFMIB_ZH_DISPLAY_TEXTS.items()
        if normalized_keyword in metric_name.casefold() or any(normalized_keyword in str(text or "").casefold() for text in display_text)
    }


class IFMIBCapabilityResolutionError(RuntimeError):
    """Raised when neither database metadata nor the manifest can decide capability."""


def _is_network_device_snmp_plugin(plugin: Any, *, raise_on_unknown: bool = False) -> bool:
    """Return the single capability decision used by IF-MIB and interface filters."""
    if plugin is None or not str(getattr(plugin, "collect_type", "")).startswith("snmp"):
        return False
    database_error = None
    try:
        if plugin.monitor_object.filter(type_id=NETWORK_DEVICE_TYPE_ID, name__in=CORE_IFMIB_OBJECT_NAMES).exists():
            return True
        if raise_on_unknown:
            identities = set(plugin.monitor_object.values_list("type_id", "name"))
            if identities and all(type_id is not None and name for type_id, name in identities):
                return False
    except (AttributeError, DatabaseError, TypeError) as exc:
        database_error = exc
        logger.warning(f"读取 SNMP 模板对象能力失败: {exc}")

    # 通用模板的存量数据库对象可能尚未补齐 type_id；回退到内置 manifest，避免
    # 已固有 IF-MIB 接口表的 Router/Firewall 等模板失去接口过滤。
    try:
        from apps.monitor.services.plugin_guide import PluginGuideService

        plugin_dir = PluginGuideService.resolve_plugin_dir(plugin)
        metrics_file = Path(plugin_dir) / "metrics.json" if plugin_dir else None
        if metrics_file is None or not metrics_file.is_file():
            if raise_on_unknown:
                raise IFMIBCapabilityResolutionError("Unable to resolve IF-MIB capability: manifest is unavailable") from database_error
            return False
        return is_ifmib_capable_plugin_data(json.loads(metrics_file.read_text(encoding="utf-8")))
    except (AttributeError, OSError, ValueError, TypeError) as exc:
        logger.warning(f"读取 SNMP 模板内置能力失败: {exc}")
        if raise_on_unknown:
            raise IFMIBCapabilityResolutionError("Unable to resolve IF-MIB capability from database or manifest") from exc
        return False


def is_ifmib_capable_plugin(plugin: Any) -> bool:
    """Return whether a network-device SNMP plugin supports public IF-MIB."""
    return _is_network_device_snmp_plugin(plugin)


def is_interface_filter_capable_plugin(plugin: Any) -> bool:
    """Only templates with IF-MIB may expose filters for the injected interface table."""
    return _is_network_device_snmp_plugin(plugin)


def resolve_interface_filter_capability_for_migration(plugin: Any) -> bool:
    """Resolve migration scope without converting unknown capability to unsupported."""
    return _is_network_device_snmp_plugin(plugin, raise_on_unknown=True)


def is_ifmib_capable_plugin_data(plugin_data: dict[str, Any]) -> bool:
    """Metadata-file adapter for the importer, with the same capability contract."""
    collect_type = str(plugin_data.get("collect_type") or "")
    return (
        str(plugin_data.get("type") or "") == NETWORK_DEVICE_TYPE_ID
        and str(plugin_data.get("name") or "") in CORE_IFMIB_OBJECT_NAMES
        and (not collect_type or collect_type.startswith("snmp"))
    )


def is_ifmib_capable_render_context(context: dict[str, Any]) -> bool:
    """Runtime adapter; Controller resolves plugin capability before template rendering."""
    return context.get("ifmib_capable") is True
