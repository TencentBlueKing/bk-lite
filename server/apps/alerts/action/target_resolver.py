from apps.rpc.node_mgmt import NodeMgmt
from apps.alerts.action.exceptions import TargetError


def resolve_node_target(host_value, team) -> dict:
    """告警主机 → 节点管理 node target。精确 IP 匹配 + 团队消歧。"""
    if not host_value:
        raise TargetError("目标主机缺失关键信息")
    query = {"ip": host_value, "skip_permission": True, "page": 1, "page_size": 50}
    if team:
        query["organization_ids"] = list(team)
    result = NodeMgmt().node_list(query) or {}
    nodes = result.get("nodes", [])
    exact = [n for n in nodes if str(n.get("ip")) == str(host_value)]
    if not exact:
        raise TargetError(f"主机[{host_value}]未纳管到节点管理")
    if len(exact) > 1:
        raise TargetError(f"主机[{host_value}]在节点管理中不唯一")
    n = exact[0]
    return {"node_id": n["id"], "name": n.get("name"), "ip": str(n["ip"]),
            "os": n.get("operating_system"), "cloud_region_id": n.get("cloud_region")}
