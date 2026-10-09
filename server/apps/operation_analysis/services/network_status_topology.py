from typing import Any

from rest_framework.exceptions import ValidationError

from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES, NETWORK_STATUS_TOPOLOGY_MAX_NODES
from apps.operation_analysis.common.get_nats_source_data import build_nats_user_info
from apps.operation_analysis.services.user_messages import oa_message
from apps.rpc.cmdb import CMDB


class NetworkStatusTopologyService:
    CLOSED_SET_ERROR = "设备列表包含无效或不允许的网络设备，请重新配置"
    ONE_HOP_ERROR = "无法获取该设备的一跳网络拓扑"

    @classmethod
    def build(
        cls,
        request,
        inst_uuids: list[str],
        node_limit: int | None = None,
        depth: int | None = None,
    ) -> dict[str, Any]:
        limit = int(node_limit or NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES)
        if limit < 1 or limit > NETWORK_STATUS_TOPOLOGY_MAX_NODES:
            raise ValidationError(
                {"node_limit": oa_message("messages.nst_node_limit", "node_limit 必须在 1 到 {limit} 之间", limit=NETWORK_STATUS_TOPOLOGY_MAX_NODES)}
            )
        unique = [str(value) for value in inst_uuids if str(value).strip()]
        if not unique or len(unique) > limit:
            raise ValidationError({"inst_uuids": oa_message("messages.nst_closed_set", cls.CLOSED_SET_ERROR)})

        if depth is not None:
            if int(depth) != 1 or len(unique) != 1:
                raise ValidationError({"depth": oa_message("messages.nst_one_hop_single", "一跳展开只接受单个 inst_uuid")})
            topology = cls._get_cmdb_one_hop(request, unique[0], limit)
            return {
                "center_id": unique[0],
                "nodes": topology.get("nodes", []),
                "links": topology.get("links", []),
                "truncated": bool(topology.get("truncated")),
                "node_limit": limit,
            }

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
            raise ValidationError({"inst_uuids": oa_message("messages.nst_closed_set", cls.CLOSED_SET_ERROR)})
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        return {
            "nodes": data.get("nodes") or [],
            "links": data.get("links") or [],
            "truncated": bool(data.get("truncated")),
        }

    @classmethod
    def _get_cmdb_one_hop(cls, request, inst_uuid: str, node_limit: int) -> dict[str, Any]:
        result = CMDB().network_topology_by_uuid(
            inst_uuid=inst_uuid,
            depth=1,
            node_limit=node_limit,
            user_info=build_nats_user_info(request),
        )
        if not isinstance(result, dict) or result.get("result") is not True:
            raise ValidationError({"inst_uuids": oa_message("messages.nst_one_hop", cls.ONE_HOP_ERROR)})
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        return {
            "nodes": data.get("nodes") or [],
            "links": data.get("links") or [],
            "truncated": bool(data.get("truncated")),
        }
