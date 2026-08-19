from typing import Any

from rest_framework.exceptions import NotFound, PermissionDenied

from apps.cmdb.constants.constants import NETWORK_TOPO_NODE_LIMIT, VIEW
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.cmdb.views.instance import InstanceViewSet


class NetworkStatusTopologyService:
    @classmethod
    def build(cls, request, model_id: str, inst_uuid: str, depth: int) -> dict[str, Any]:
        topology = cls._get_cmdb_topology(request, model_id, inst_uuid, depth)
        center = topology.get("center") or {}
        return {
            "center_id": str(center.get("id") or inst_uuid),
            "center_model_id": str(center.get("model_id") or model_id),
            "nodes": topology.get("nodes", []),
            "links": topology.get("links", []),
            "truncated": bool(topology.get("truncated", False)),
            "node_limit": NETWORK_TOPO_NODE_LIMIT,
        }

    @staticmethod
    def _get_cmdb_topology(request, model_id: str, inst_uuid: str, depth: int) -> dict[str, Any]:
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
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
        return InstanceManage.network_topology_by_uuid(
            inst_uuid,
            instance["model_id"],
            depth=depth,
            permission_map=permissions_map,
            user=request.user,
        )
