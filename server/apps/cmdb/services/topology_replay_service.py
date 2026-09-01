"""拓扑通道重放：由轮次完成标记触发，不改 Network 任务 exec_status。"""

from __future__ import annotations

from typing import Any

from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics
from apps.cmdb.collection.metrics_cannula import MetricsCannula
from apps.cmdb.collection.query_vm import Collection
from apps.cmdb.collection.round_sync import cmdb_instance_id, query_latest_round_ts
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import COLLECTION_ROLE_TOPOLOGY, CollectModels, normalize_topology_contract
from apps.core.logger import cmdb_logger as logger

LAST_SYNCED_TOPOLOGY_ROUND_KEY = "last_synced_topology_round"
PENDING_TOPOLOGY_REPLAY_KEY = "_topology_replay_pending"


def query_role_round_marker(
    instance_id: str,
    *,
    collection_role: str,
    collection: Collection | None = None,
) -> dict[str, Any] | None:
    """返回最新标记的 {round_ts, channel_config_version}。"""
    from apps.cmdb.collection.round_sync import ROUND_COMPLETE_METRIC

    coll = collection or Collection()
    sql = f"{ROUND_COMPLETE_METRIC}{{instance_id='{instance_id}'," f"collection_role='{collection_role}'}}"
    try:
        payload = coll.query(sql)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[TopoReplay] 查询标记失败 instance_id=%s role=%s error=%s",
            instance_id,
            collection_role,
            type(exc).__name__,
        )
        return None
    rows = ((payload or {}).get("data") or {}).get("result") or []
    best = None
    best_ts = None
    for row in rows:
        metric = row.get("metric") or {}
        value = (row.get("value") or [None, None])[1]
        try:
            ts = int(float(value))
        except (TypeError, ValueError):
            continue
        if best_ts is None or ts > best_ts:
            best_ts = ts
            best = {
                "round_ts": ts,
                "channel_config_version": str(metric.get("channel_config_version") or ""),
            }
    return best


def get_last_synced_topology_round(collect_digest: Any) -> int | None:
    if not isinstance(collect_digest, dict):
        return None
    value = collect_digest.get(LAST_SYNCED_TOPOLOGY_ROUND_KEY)
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _interfaces_ready(task: CollectModels) -> bool:
    format_data = task.format_data if isinstance(task.format_data, dict) else {}
    for bucket in ("add", "update"):
        for row in format_data.get(bucket) or []:
            if isinstance(row, dict) and (row.get("model_id") == "interface" or str(row.get("__name__", "")).startswith("network_interfaces")):
                return True
    raw = format_data.get("__raw_data__") or []
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get("__name__", "") or "")
        if "network_interfaces" in name or row.get("model_id") == "interface":
            return True
    # 兼容：任务曾成功入库过（有 digest 计数）也允许尝试
    digest = task.collect_digest if isinstance(task.collect_digest, dict) else {}
    return int(digest.get("all") or 0) > 0 or int(digest.get("collect_success") or 0) > 0


def _set_pending(task: CollectModels, marker: dict[str, Any]) -> None:
    params = dict(task.params or {})
    params[PENDING_TOPOLOGY_REPLAY_KEY] = {
        "round_ts": marker.get("round_ts"),
        "channel_config_version": marker.get("channel_config_version"),
    }
    CollectModels._default_manager.filter(id=task.id).update(params=params)


def _clear_pending(task: CollectModels) -> None:
    params = dict(task.params or {})
    if PENDING_TOPOLOGY_REPLAY_KEY not in params:
        return
    params.pop(PENDING_TOPOLOGY_REPLAY_KEY, None)
    CollectModels._default_manager.filter(id=task.id).update(params=params)


def _mark_topology_synced(task: CollectModels, round_ts: int) -> None:
    digest = dict(task.collect_digest or {})
    digest[LAST_SYNCED_TOPOLOGY_ROUND_KEY] = int(round_ts)
    CollectModels._default_manager.filter(id=task.id).update(collect_digest=digest)


class TopologyReplayCollector(CollectNetworkMetrics):
    """强制拓扑重放插件。"""

    def __init__(self, inst_name, inst_id, task_id, *args, **kwargs):
        kwargs["force_topology_replay"] = True
        super().__init__(inst_name, inst_id, task_id, *args, **kwargs)


def replay_topology_for_task(
    task_id: int,
    *,
    marker: dict[str, Any] | None = None,
    force: bool = False,
) -> str:
    """幂等拓扑重放。返回 played / pending / stale / skipped / missing / error。"""
    task = CollectModels._default_manager.filter(id=task_id).first()
    if task is None:
        logger.info("[TopoReplay] 任务不存在，忽略 task_id=%s", task_id)
        return "missing"
    if task.model_id != "network" and task.task_type != CollectPluginTypes.SNMP:
        return "skipped"

    contract = normalize_topology_contract(task.params or {})
    if not contract["has_network_topo"]:
        logger.info("[TopoReplay] 拓扑已关闭，忽略 task_id=%s", task_id)
        _clear_pending(task)
        return "stale"

    instance_id = cmdb_instance_id(task_id)
    marker = marker or query_role_round_marker(instance_id, collection_role=COLLECTION_ROLE_TOPOLOGY)
    if not marker:
        # 兼容旧 agent：无 role 标签时用无过滤标记 + 有 topo 指标时也尝试
        fallback_ts = query_latest_round_ts(instance_id)
        if fallback_ts is None:
            logger.info("[TopoReplay] 无拓扑完成标记 task_id=%s", task_id)
            return "skipped"
        marker = {"round_ts": fallback_ts, "channel_config_version": ""}

    current_version = str(contract.get("topology_channel_config_version") or "1")
    marker_version = str(marker.get("channel_config_version") or "")
    if marker_version and marker_version != current_version and not force:
        logger.info(
            "[TopoReplay] 版本过期 stale task_id=%s marker_version=%s current=%s",
            task_id,
            marker_version,
            current_version,
        )
        return "stale"

    round_ts = marker.get("round_ts")
    last = get_last_synced_topology_round(task.collect_digest)
    if last is not None and round_ts is not None and int(round_ts) == int(last) and not force:
        logger.info("[TopoReplay] 同轮次已重放 task_id=%s round_ts=%s", task_id, round_ts)
        return "skipped"

    if not _interfaces_ready(task):
        _set_pending(task, marker)
        logger.info("[TopoReplay] 设备/接口未就绪，进入 pending task_id=%s", task_id)
        return "pending"

    try:
        organization = task.team or []
        cannula = MetricsCannula(
            inst_id=None,
            organization=organization if isinstance(organization, list) else [organization],
            inst_name=None,
            task_id=task_id,
            collect_plugin=TopologyReplayCollector,
            filter_collect_task=True,
            data_cleanup_strategy=task.data_cleanup_strategy,
            plugin_kwargs={"collect_inst": task, "round_ts": round_ts},
        )
        cannula.collect_controller()
        _clear_pending(task)
        if round_ts is not None:
            # 重新读 digest，避免覆盖设备对账刚写入的字段
            fresh = CollectModels._default_manager.filter(id=task_id).values_list("collect_digest", flat=True).first()
            digest = dict(fresh or {})
            digest[LAST_SYNCED_TOPOLOGY_ROUND_KEY] = int(round_ts)
            CollectModels._default_manager.filter(id=task_id).update(collect_digest=digest)
        logger.info("[TopoReplay] 重放成功 task_id=%s round_ts=%s", task_id, round_ts)
        return "played"
    except Exception:  # noqa: BLE001
        logger.exception("[TopoReplay] 重放失败，保留上一轮关系 task_id=%s", task_id)
        _set_pending(task, marker)
        return "error"


def wake_pending_topology_replay(task_id: int) -> str | None:
    task = CollectModels._default_manager.filter(id=task_id).only("id", "params").first()
    if task is None:
        return None
    pending = (task.params or {}).get(PENDING_TOPOLOGY_REPLAY_KEY)
    if not isinstance(pending, dict) or not pending.get("round_ts"):
        return None
    return replay_topology_for_task(
        task_id,
        marker={
            "round_ts": pending.get("round_ts"),
            "channel_config_version": pending.get("channel_config_version"),
        },
    )


def maybe_replay_topology_from_gate(task_id: int, params: dict | None, collect_digest: dict | None) -> str | None:
    contract = normalize_topology_contract(params or {})
    if not contract.get("has_network_topo"):
        return None
    instance_id = cmdb_instance_id(task_id)
    marker = query_role_round_marker(instance_id, collection_role=COLLECTION_ROLE_TOPOLOGY)
    if not marker:
        return None
    last = get_last_synced_topology_round(collect_digest)
    if last is not None and int(marker["round_ts"]) == int(last):
        return "skipped"
    return replay_topology_for_task(task_id, marker=marker)
