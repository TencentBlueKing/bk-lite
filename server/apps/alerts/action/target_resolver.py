from apps.rpc.node_mgmt import NodeMgmt
from apps.alerts.action.exceptions import TargetError


def resolve_effective_team(alert_team, rule_team) -> list[int]:
    """计算动作允许使用的最小组织范围；告警组织是不可放大的安全边界。"""
    alert_ids = {int(team_id) for team_id in (alert_team or [])}
    rule_ids = {int(team_id) for team_id in (rule_team or [])}
    if not alert_ids:
        raise TargetError("告警缺少组织上下文，拒绝执行远程动作")
    effective = alert_ids & rule_ids if rule_ids else alert_ids
    if not effective:
        raise TargetError("动作规则与告警组织不匹配")
    return sorted(effective)


def resolve_node_target(host_value, team) -> dict:
    """告警主机 → 节点管理 node target。精确 IP 匹配 + 团队消歧。"""
    if not host_value:
        raise TargetError("目标主机缺失关键信息")
    if not team:
        raise TargetError("目标主机查询缺少组织上下文")
    query = {
        "ip": host_value,
        "skip_permission": True,
        "organization_ids": list(team),
        "page": 1,
        "page_size": 50,
    }
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
