"""节点只读目录查询。在线状态与节点列表一致：60 秒内心跳。"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.node_mgmt.models import (
    CloudRegion,
    Collector,
    Node,
    NodeCollectorInstallStatus,
    NodeComponentVersion,
)
from apps.node_mgmt.services.node_status_filter import ACTIVE_WINDOW_SECONDS, hosted_collectors_for_filter


def team_ids(team):
    ids = []
    for item in team or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0:
            ids.append(value)
    return ids


def list_cloud_regions(*, team, page, page_size, keyword):
    if not team_ids(team):
        return _empty_page(page, page_size)
    queryset = CloudRegion.objects.all().order_by("id")
    if keyword:
        queryset = queryset.filter(name__icontains=keyword)
    total = queryset.count()
    start = (page - 1) * page_size
    items = [_region_item(row) for row in queryset[start : start + page_size]]
    return {"count": total, "page": page, "page_size": page_size, "items": items}


def list_nodes(*, team, page, page_size, keyword, cloud_region_id=None):
    queryset = _node_queryset(team, keyword, cloud_region_id)
    total = queryset.count()
    start = (page - 1) * page_size
    rows = list(queryset[start : start + page_size])
    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "items": _project_nodes(rows),
    }


def get_node(*, team, node_id):
    node = _node_queryset(team, "", None).filter(id=node_id).first()
    if node is None:
        return {"result": False, "message": "节点不存在"}
    return _project_nodes([node])[0]


def _node_queryset(team, keyword, cloud_region_id):
    ids = team_ids(team)
    if not ids:
        return Node.objects.none()
    queryset = Node.objects.filter(nodeorganization__organization__in=ids).distinct().order_by("name", "id")
    if cloud_region_id:
        queryset = queryset.filter(cloud_region_id=cloud_region_id)
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(ip__icontains=keyword))
    return queryset


def _project_nodes(nodes):
    node_ids = [node.id for node in nodes]
    collector_name_by_id = dict(Collector.objects.values_list("id", "name"))
    install_by_node = {}
    for row in NodeCollectorInstallStatus.objects.filter(node_id__in=node_ids).values("node_id", "collector_id", "status"):
        install_by_node.setdefault(row["node_id"], []).append(row)
    controllers_by_node = {}
    for version in NodeComponentVersion.objects.filter(node_id__in=node_ids, component_type="controller").order_by("component_id"):
        controllers_by_node.setdefault(version.node_id, []).append(
            {
                "component_id": version.component_id,
                "version": version.version,
                "upgradeable": version.upgradeable,
            }
        )
    cutoff = timezone.now() - timedelta(seconds=ACTIVE_WINDOW_SECONDS)
    items = []
    for node in nodes:
        reported = node.status.get("collectors") if isinstance(node.status, dict) else None
        collectors = hosted_collectors_for_filter(reported, install_by_node.get(node.id, []), collector_name_by_id)
        items.append(
            {
                "id": node.id,
                "name": node.name,
                "ip": node.ip,
                "operating_system": node.operating_system,
                "cpu_architecture": node.cpu_architecture,
                "cloud_region_id": node.cloud_region_id,
                "node_type": node.node_type,
                "install_method": node.install_method,
                "online": bool(node.updated_at and node.updated_at > cutoff),
                "collectors": [
                    {
                        "collector_id": item["collector_id"],
                        "collector_name": item["collector_name"],
                        "status": item["status"],
                    }
                    for item in collectors
                ],
                "controllers": controllers_by_node.get(node.id, []),
            }
        )
    return items


def _region_item(region):
    return {"id": region.id, "name": region.name, "introduction": region.introduction}


def _empty_page(page, page_size):
    return {"count": 0, "page": page, "page_size": page_size, "items": []}
