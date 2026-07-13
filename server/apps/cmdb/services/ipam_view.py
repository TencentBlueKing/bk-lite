# -- coding: utf-8 --
"""IP 视图数据组装：容量/利用率/各状态计数/落库 IP 列表。规格 §5/§7.2。"""
from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.utils.ipam_cidr import parse_subnet, subnet_capacity, compute_utilization

IP_STATUS_KEYS = ["online", "offline", "conflict", "unknown"]


def _dedupe_ip_rows(rows: list) -> list:
    result = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        identity = row.get("_id") or (row.get("subnet_id"), row.get("ip_addr"))
        if identity in seen:
            continue
        seen.add(identity)
        result.append(row)
    return result


def _query_subnet_ips_by_field(subnet_inst_id) -> list:
    with GraphClient() as ag:
        rows, _ = ag.query_entity(
            INSTANCE,
            [{"field": "model_id", "type": "str=", "value": "ip"},
             {"field": "subnet_id", "type": "str=", "value": str(subnet_inst_id)}],
        )
    return rows or []


def _query_subnet_ips_by_association(subnet_inst_id) -> list:
    associations = InstanceManage.instance_association_instance_list("subnet", int(subnet_inst_id)) or []
    rows = []
    for item in associations:
        if item.get("model_asst_id") != "subnet_group_ip":
            continue
        rows.extend(item.get("inst_list") or [])
    return rows


def _query_subnet_ips(subnet_inst_id) -> list:
    """IP 视图按实例关联查询；旧数据用 subnet_id 字段兜底。"""
    return _dedupe_ip_rows(_query_subnet_ips_by_association(subnet_inst_id) + _query_subnet_ips_by_field(subnet_inst_id))


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
