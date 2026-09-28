from __future__ import annotations

from typing import Any

NETWORK_COLLECTION_ASSET_MODELS = frozenset({"switch", "router", "firewall", "loadbalance"})


def _manage_ip(instance: dict[str, Any]) -> str:
    for field in ("ip_addr", "ip", "host"):
        value = str(instance.get(field) or "").strip()
        if value:
            return value
    return ""


def validate_network_collection_assets(instances) -> None:
    """校验 Network 任务资产模式目标：仅四类网络设备，且管理 IP 不重复。"""
    if not instances:
        return
    if not isinstance(instances, list):
        raise ValueError("实例目标必须为列表")

    seen_ips: dict[str, str] = {}
    for instance in instances:
        if not isinstance(instance, dict):
            raise ValueError("实例目标格式错误")
        model_id = str(instance.get("model_id") or "").strip()
        if model_id not in NETWORK_COLLECTION_ASSET_MODELS:
            raise ValueError("采集任务仅支持交换机、路由器、防火墙、负载均衡实例")
        manage_ip = _manage_ip(instance)
        if not manage_ip:
            raise ValueError("所选资产缺少管理IP")
        previous = seen_ips.get(manage_ip)
        if previous is not None:
            raise ValueError(f"同一任务中管理 IP 不能重复: {manage_ip}")
        seen_ips[manage_ip] = model_id
