from typing import Any

from rest_framework.exceptions import ValidationError

from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES, NETWORK_STATUS_TOPOLOGY_MAX_NODES
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import operation_analysis_logger as logger


class NetworkStatusTopologyService:
    CLOSED_SET_ERROR = "设备列表包含无效或不允许的网络设备，请重新配置"

    @classmethod
    def build(cls, request, inst_uuids: list[str], node_limit: int | None = None) -> dict[str, Any]:
        limit = int(node_limit or NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES)
        if limit < 1 or limit > NETWORK_STATUS_TOPOLOGY_MAX_NODES:
            raise ValidationError({"node_limit": f"node_limit 必须在 1 到 {NETWORK_STATUS_TOPOLOGY_MAX_NODES} 之间"})
        unique = [str(value) for value in inst_uuids if str(value).strip()]
        if not unique or len(unique) > limit:
            raise ValidationError({"inst_uuids": cls.CLOSED_SET_ERROR})

        topology = cls._get_cmdb_topology(request, unique)
        return {
            "nodes": topology.get("nodes", []),
            "links": topology.get("links", []),
            "truncated": False,
            "node_limit": limit,
        }

    @classmethod
    def _get_cmdb_topology(cls, request, inst_uuids: list[str]) -> dict[str, Any]:
        entities = InstanceManage.query_entity_by_uuids(inst_uuids)
        if len(entities) != len(inst_uuids):
            raise ValidationError({"inst_uuids": cls.CLOSED_SET_ERROR})

        permission_maps: dict[str, dict] = {}
        for entity in entities:
            model_id = str(entity.get("model_id") or "")
            if model_id and model_id not in permission_maps:
                permission_maps[model_id] = CmdbRulesFormatUtil.format_user_groups_permissions(
                    request=request,
                    model_id=model_id,
                )

        try:
            return InstanceManage.network_topology_among_uuids(
                inst_uuids,
                permission_maps=permission_maps,
                user=request.user,
            )
        except BaseAppException as exc:
            logger.info("network status topology closed set rejected: %s", exc)
            raise ValidationError({"inst_uuids": cls.CLOSED_SET_ERROR}) from exc
