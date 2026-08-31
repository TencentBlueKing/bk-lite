"""Network 采集任务双通道节点配置对账。"""

from __future__ import annotations

from typing import Any

from apps.cmdb.models.collect_model import (
    COLLECTION_ROLE_DEVICE,
    COLLECTION_ROLE_TOPOLOGY,
    normalize_topology_contract,
    recommended_topology_interval_minutes,
)
from apps.cmdb.node_configs.network.network import NetworkNodeParams, NetworkTopoNodeParams
from apps.core.logger import cmdb_logger as logger
from apps.rpc.node_mgmt import NodeMgmt


def network_device_config_id(task_id: int | str) -> str:
    return f"cmdb_{task_id}"


def network_topology_config_id(task_id: int | str) -> str:
    return f"cmdb_{task_id}_topology"


def ensure_topology_interval_defaults(instance) -> dict[str, Any]:
    """存量任务补齐拓扑周期字段（不强制写库，调用方可 persist）。"""
    params = dict(getattr(instance, "params", None) or {})
    device_minutes = None
    if getattr(instance, "cycle_value_type", "") == "cycle":
        try:
            device_minutes = int(instance.cycle_value)
        except (TypeError, ValueError):
            device_minutes = None
    normalized = normalize_topology_contract(params, device_cycle_minutes=device_minutes)
    if params.get("topology_interval_minutes") in (None, "") and normalized["has_network_topo"]:
        normalized["topology_interval_minutes"] = recommended_topology_interval_minutes(device_minutes)
        normalized["topology_interval_mode"] = params.get("topology_interval_mode") or "recommended"
    changed = any(params.get(key) != normalized.get(key) for key in normalized)
    params.update(normalized)
    return params if changed or True else params


def bump_channel_versions(params: dict, *, device: bool = False, topology: bool = False) -> dict:
    updated = dict(params or {})
    if device:
        updated["device_channel_config_version"] = int(updated.get("device_channel_config_version") or 1) + 1
    if topology:
        updated["topology_channel_config_version"] = int(updated.get("topology_channel_config_version") or 1) + 1
    return updated


def expected_network_node_configs(instance) -> list[dict]:
    """按期望集合生成节点配置 payload（device 必有；topology 视开关）。"""
    params = ensure_topology_interval_defaults(instance)
    instance.params = params
    nodes = NetworkNodeParams(instance).push_params()
    contract = normalize_topology_contract(params)
    if contract["has_network_topo"]:
        nodes.extend(NetworkTopoNodeParams(instance).push_params())
    return nodes


def reconcile_network_collection_configs(instance, *, delete: bool = False) -> dict[str, Any]:
    """
    将一条 Network 任务对账到期望节点配置集合。

    delete=True 时始终清理 cmdb_T 与 cmdb_T_topology，不依赖当前开关。
    """
    node_mgmt = NodeMgmt()
    task_id = instance.id
    device_id = network_device_config_id(task_id)
    topo_id = network_topology_config_id(task_id)
    result = {"device_id": device_id, "topology_id": topo_id, "pushed": [], "deleted": []}

    if delete:
        config_ids = [device_id, topo_id]
        try:
            node_mgmt.delete_child_configs(config_ids)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[NetworkReconcile] 删除节点配置失败 task_id=%s config_ids=%s error_type=%s",
                task_id,
                config_ids,
                type(exc).__name__,
            )
            raise
        result["deleted"].extend(config_ids)
        return result

    # 先删拓扑配置再整体推送，避免关拓扑后残留。
    contract = normalize_topology_contract(ensure_topology_interval_defaults(instance))
    if not contract["has_network_topo"]:
        try:
            node_mgmt.delete_child_configs([topo_id])
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[NetworkReconcile] 清理拓扑配置失败 task_id=%s config_id=%s error_type=%s",
                task_id,
                topo_id,
                type(exc).__name__,
            )
            raise
        result["deleted"].append(topo_id)

    nodes = expected_network_node_configs(instance)
    if nodes:
        node_mgmt.batch_add_node_child_config(nodes)
        result["pushed"] = [node.get("id") for node in nodes]
        logger.info(
            "[NetworkReconcile] 对账完成 task_id=%s roles=%s configs=%s",
            task_id,
            [COLLECTION_ROLE_DEVICE] + ([COLLECTION_ROLE_TOPOLOGY] if contract["has_network_topo"] else []),
            result["pushed"],
        )
    return result
