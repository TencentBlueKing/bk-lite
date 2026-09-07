from typing import Any

from rest_framework.exceptions import ValidationError

from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES, NETWORK_STATUS_TOPOLOGY_MAX_NODES
from apps.operation_analysis.common.get_nats_source_data import build_nats_user_info
from apps.rpc.cmdb import CMDB


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
        result = CMDB().network_topology_among_uuids(
            inst_uuids=inst_uuids,
            user_info=build_nats_user_info(request),
        )
        if not isinstance(result, dict) or result.get("result") is not True:
            raise ValidationError({"inst_uuids": cls.CLOSED_SET_ERROR})
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        return {
            "nodes": data.get("nodes") or [],
            "links": data.get("links") or [],
            "truncated": bool(data.get("truncated")),
        }
