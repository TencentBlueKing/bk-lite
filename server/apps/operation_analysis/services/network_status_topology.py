from typing import Any

from rest_framework.exceptions import NotFound, PermissionDenied

from apps.alerts.constants import AlertStatus
from apps.alerts.views.alert import AlertModelViewSet
from apps.cmdb.constants.constants import NETWORK_TOPO_NODE_LIMIT, VIEW
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.cmdb.views.instance import InstanceViewSet

ALERT_LEVEL_PRIORITY = {"0": 0, "1": 1, "2": 2}


def map_alert_level_to_node_status(level: str | int | None) -> dict[str, Any]:
    level_key = None if level is None else str(level)
    if level_key == "0":
        return {"status": "critical", "severity": "critical", "pulse": True, "color": "red"}
    if level_key == "1":
        return {"status": "error", "severity": "error", "pulse": False, "color": "red"}
    if level_key == "2":
        return {"status": "warning", "severity": "warning", "pulse": False, "color": "yellow"}
    return {"status": "normal", "severity": None, "pulse": False, "color": "green"}


class NetworkStatusTopologyService:
    @classmethod
    def build(cls, request, model_id: str, inst_id: int, depth: int) -> dict[str, Any]:
        topology = cls._get_cmdb_topology(request, model_id, inst_id, depth)
        node_keys = {
            (str(node.get("model_id")), str(node.get("id")))
            for node in topology.get("nodes", [])
            if node.get("model_id") is not None and node.get("id") is not None
        }
        alert_summary = cls._get_active_alert_summary(request, node_keys)

        nodes = []
        for node in topology.get("nodes", []):
            node_key = (str(node.get("model_id")), str(node.get("id")))
            summary = alert_summary.get(node_key, {"count": 0, "max_level": None})
            nodes.append(
                {
                    **node,
                    "alert_count": summary["count"],
                    **map_alert_level_to_node_status(summary["max_level"]),
                }
            )

        center = topology.get("center") or {}
        return {
            "center_id": str(center.get("id") or inst_id),
            "center_model_id": str(center.get("model_id") or model_id),
            "nodes": nodes,
            "links": topology.get("links", []),
            "truncated": bool(topology.get("truncated", False)),
            "node_limit": NETWORK_TOPO_NODE_LIMIT,
        }

    @staticmethod
    def _get_cmdb_topology(request, model_id: str, inst_id: int, depth: int) -> dict[str, Any]:
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if not instance:
            raise NotFound("实例不存在")

        instance_view = InstanceViewSet()
        permission_error = instance_view.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            raise PermissionDenied("抱歉！您没有此实例的权限")

        permissions_map = CmdbRulesFormatUtil.format_user_groups_permissions(
            request=request,
            model_id=instance["model_id"],
        )
        return InstanceManage.network_topology(
            int(inst_id),
            instance["model_id"],
            depth=depth,
            permission_map=permissions_map,
            user=request.user,
        )

    @staticmethod
    def _get_active_alert_summary(request, node_keys: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
        if not node_keys:
            return {}

        alert_view = AlertModelViewSet()
        queryset = alert_view.get_queryset_by_permission(request, alert_view.get_queryset())
        resource_types = {resource_type for resource_type, _resource_id in node_keys}
        resource_ids = {resource_id for _resource_type, resource_id in node_keys}
        queryset = queryset.filter(
            status__in=AlertStatus.ACTIVATE_STATUS,
            resource_type__in=resource_types,
            resource_id__in=resource_ids,
        )

        summary: dict[tuple[str, str], dict[str, Any]] = {}
        for alert in queryset.values("resource_type", "resource_id", "level"):
            node_key = (str(alert["resource_type"]), str(alert["resource_id"]))
            if node_key not in node_keys:
                continue

            node_summary = summary.setdefault(node_key, {"count": 0, "max_level": None})
            node_summary["count"] += 1
            level = None if alert["level"] is None else str(alert["level"])
            if level not in ALERT_LEVEL_PRIORITY:
                continue
            current = node_summary["max_level"]
            if current is None or ALERT_LEVEL_PRIORITY[level] < ALERT_LEVEL_PRIORITY[str(current)]:
                node_summary["max_level"] = level

        return summary
