"""公共 IF-MIB 能力与指标来源的唯一判定入口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.db import DatabaseError

from apps.core.logger import monitor_logger as logger

NETWORK_DEVICE_TYPE_ID = "Network Device"
COMMON_IFMIB_METRIC_NAMES = frozenset(
    {
        "interface_ifAdminStatus", "interface_ifOperStatus", "interface_ifSpeed",
        "interface_ifInErrors", "interface_ifOutErrors", "interface_ifInDiscards",
        "interface_ifOutDiscards", "interface_ifInUcastPkts", "interface_ifOutUcastPkts",
        "interface_ifInOctets", "interface_ifOutOctets", "interface_ifHCInOctets",
        "interface_ifHCOutOctets", "device_total_incoming_traffic",
        "device_total_outgoing_traffic",
    }
)

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


def _is_network_device_snmp_plugin(plugin: Any) -> bool:
    """Return the single capability decision used by IF-MIB and interface filters."""
    if plugin is None or not str(getattr(plugin, "collect_type", "")).startswith("snmp"):
        return False
    try:
        if plugin.monitor_object.filter(type_id=NETWORK_DEVICE_TYPE_ID).exists():
            return True
    except (AttributeError, DatabaseError, TypeError) as exc:
        logger.warning(f"读取 SNMP 模板对象能力失败: {exc}")

    # 通用模板的存量数据库对象可能尚未补齐 type_id；回退到内置 manifest，避免
    # 已固有 IF-MIB 接口表的 Router/Firewall 等模板失去接口过滤。
    try:
        from apps.monitor.services.plugin_guide import PluginGuideService

        plugin_dir = PluginGuideService.resolve_plugin_dir(plugin)
        metrics_file = Path(plugin_dir) / "metrics.json" if plugin_dir else None
        if metrics_file is None or not metrics_file.is_file():
            return False
        return json.loads(metrics_file.read_text(encoding="utf-8")).get("type") == NETWORK_DEVICE_TYPE_ID
    except (AttributeError, OSError, ValueError, TypeError) as exc:
        logger.warning(f"读取 SNMP 模板内置能力失败: {exc}")
        return False


def is_ifmib_capable_plugin(plugin: Any) -> bool:
    """Return whether a network-device SNMP plugin supports public IF-MIB."""
    return _is_network_device_snmp_plugin(plugin)


def is_interface_filter_capable_plugin(plugin: Any) -> bool:
    """Only templates with IF-MIB may expose filters for the injected interface table."""
    return _is_network_device_snmp_plugin(plugin)


def is_ifmib_capable_plugin_data(plugin_data: dict[str, Any]) -> bool:
    """Metadata-file adapter for the importer, with the same capability contract."""
    collect_type = str(plugin_data.get("collect_type") or "")
    return (
        str(plugin_data.get("type") or "") == NETWORK_DEVICE_TYPE_ID
        and (not collect_type or collect_type.startswith("snmp"))
    )


def is_ifmib_capable_render_context(context: dict[str, Any]) -> bool:
    """Runtime adapter; Controller resolves plugin capability before template rendering."""
    return context.get("ifmib_capable") is True
