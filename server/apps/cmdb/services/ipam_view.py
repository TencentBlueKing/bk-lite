# -- coding: utf-8 --
"""IP 视图数据组装：容量/利用率/各状态计数/落库 IP 列表。规格 §5/§7.2。"""
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.utils.ipam_cidr import parse_subnet, subnet_capacity, compute_utilization

IP_STATUS_KEYS = ["online", "offline", "conflict", "unknown"]


def _query_subnet_ips(subnet_inst_id) -> list:
    with GraphClient() as ag:
        rows, _ = ag.query_entity(
            INSTANCE,
            [{"field": "model_id", "type": "str=", "value": "ip"},
             {"field": "subnet_id", "type": "str=", "value": str(subnet_inst_id)}],
        )
    return rows or []


def _first(value):
    """枚举字段在库内为 list，取首值。"""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def build_ipam_view(subnet: dict) -> dict:
    net = parse_subnet(subnet.get("subnet_address"), subnet.get("subnet_mask"))
    capacity = subnet_capacity(net)
    ips = _query_subnet_ips(subnet.get("_id"))
    counts = {k: 0 for k in IP_STATUS_KEYS}
    for ip in ips:
        st = _first(ip.get("ip_status")) or "unknown"
        counts[st] = counts.get(st, 0) + 1
    util = compute_utilization(capacity, len(ips))
    return {
        "subnet_address": subnet.get("subnet_address"),
        "subnet_mask": subnet.get("subnet_mask"),
        "prefixlen": net.prefixlen,
        "capacity": capacity,
        "used": util["used"],
        "available": util["available"],
        "ratio": util["ratio"],
        "status_counts": counts,
        "ips": ips,
    }
