"""CMDB 采集轮次守门：标记查询、任务判定与兼容回退。"""

from __future__ import annotations

from typing import Any

from apps.cmdb.collection.query_vm import Collection
from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.core.logger import cmdb_logger as logger

ROUND_COMPLETE_METRIC = "cmdb_round_complete_gauge"
LAST_SYNCED_ROUND_KEY = "last_synced_round"
GATE_PAGE_SIZE = 200
ORPHAN_BEAT_PURGE_LIMIT = 500
SYNC_BEAT_NAME_PREFIX = "sync_collect_task_"

# 走 VictoriaMetrics 对账的任务类型；config_file 等 NATS 直推链路不在守门范围。
_NON_VM_RECONCILED_TASK_TYPES = frozenset({CollectPluginTypes.CONFIG_FILE})


def uses_vm_reconciliation(task_or_type) -> bool:
    task_type = getattr(task_or_type, "task_type", task_or_type)
    return task_type not in _NON_VM_RECONCILED_TASK_TYPES


def cmdb_instance_id(task_id: int | str) -> str:
    return f"cmdb_{task_id}"


def get_last_synced_round(collect_digest: Any) -> int | None:
    if not isinstance(collect_digest, dict):
        return None
    value = collect_digest.get(LAST_SYNCED_ROUND_KEY)
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def query_latest_round_ts(
    instance_id: str,
    *,
    collection: Collection | None = None,
    collection_role: str | None = None,
) -> int | None:
    """查 VictoriaMetrics 中该任务最新轮次完成标记的 value（即 round_ts）。"""
    coll = collection or Collection()
    if collection_role:
        sql = f"{ROUND_COMPLETE_METRIC}{{instance_id='{instance_id}'," f"collection_role='{collection_role}'}}"
    else:
        sql = f"{ROUND_COMPLETE_METRIC}{{instance_id='{instance_id}'}}"
    try:
        payload = coll.query(sql)
    except Exception as exc:  # noqa: BLE001 - 守门不得因单次 VM 抖动中断整轮
        logger.warning(
            "[RoundGate] 查询轮次标记失败 instance_id=%s role=%s error=%s",
            instance_id,
            collection_role or "-",
            type(exc).__name__,
        )
        return None
    rows = ((payload or {}).get("data") or {}).get("result") or []
    if not rows:
        return None
    best: int | None = None
    for row in rows:
        value = (row.get("value") or [None, None])[1]
        try:
            ts = int(float(value))
        except (TypeError, ValueError):
            continue
        if best is None or ts > best:
            best = ts
    return best


def has_instance_vm_data(instance_id: str, *, collection: Collection | None = None) -> bool:
    """兼容回退：旧 agent 无标记时，判断时序库是否已有该 instance_id 的数据。"""
    coll = collection or Collection()
    sql = f"count({{instance_id='{instance_id}'}})"
    try:
        payload = coll.query(sql)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[RoundGate] 查询 instance 数据失败 instance_id=%s error=%s",
            instance_id,
            type(exc).__name__,
        )
        return False
    rows = ((payload or {}).get("data") or {}).get("result") or []
    for row in rows:
        value = (row.get("value") or [None, None])[1]
        try:
            if float(value) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def decide_gate_action(
    *,
    exec_status: int | str,
    round_ts: int | None,
    last_synced_round: int | None,
    has_vm_data: bool,
) -> str:
    """返回 skip_running / skip_incomplete / skip_same_round / sync_round / sync_compat / skip_idle。"""
    if exec_status == CollectRunStatusType.RUNNING:
        return "skip_running"
    if round_ts is None:
        if last_synced_round is not None:
            return "skip_incomplete"
        if has_vm_data:
            return "sync_compat"
        return "skip_idle"
    if last_synced_round is not None and int(round_ts) == int(last_synced_round):
        return "skip_same_round"
    return "sync_round"
