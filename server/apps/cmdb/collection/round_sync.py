"""CMDB 采集轮次守门：标记查询、任务判定与兼容回退。"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from apps.cmdb.collection.query_vm import Collection
from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.core.logger import cmdb_logger as logger

ROUND_COMPLETE_METRIC = "cmdb_round_complete_gauge"
LAST_SYNCED_ROUND_KEY = "last_synced_round"
GATE_PAGE_SIZE = 200
ORPHAN_BEAT_PURGE_LIMIT = 500
SYNC_BEAT_NAME_PREFIX = "sync_collect_task_"
ROUND_RECOVERY_SECONDS = 24 * 60 * 60
ROUND_GATE_INTERVAL_SECONDS = 5 * 60
ROUND_MARKER_BUFFER_SECONDS = 2 * 60
VM_RETENTION_SECONDS = 7 * 24 * 60 * 60
ROUND_MARKER_QUERY_TIMEOUT_SECONDS = 10
ROUND_MARKER_QUERY_RETRIES = 1
SNAPSHOT_CONTRACT_LABEL = "snapshot_contract_version"
SNAPSHOT_CONTRACT_VERSION = "2"

# 走 VictoriaMetrics 对账的任务类型；config_file 等 NATS 直推链路不在守门范围。
_NON_VM_RECONCILED_TASK_TYPES = frozenset(
    {
        CollectPluginTypes.CONFIG_FILE,
        CollectPluginTypes.K8S,
    }
)


@dataclass(frozen=True)
class CompletedRound:
    started_at: int
    completed_at: float
    labels: dict[str, str] = field(default_factory=dict, compare=False, repr=False)

    @property
    def snapshot_complete(self) -> bool:
        """只有新协议标记能证明该轮次允许执行破坏性差异。"""
        return self.labels.get(SNAPSHOT_CONTRACT_LABEL) == SNAPSHOT_CONTRACT_VERSION


def uses_vm_reconciliation(task_or_type) -> bool:
    task_type = getattr(task_or_type, "task_type", task_or_type)
    return task_type not in _NON_VM_RECONCILED_TASK_TYPES


def completed_round_lookback_seconds(
    *,
    is_interval: bool,
    cycle_value_type: str | None,
    cycle_value: Any,
) -> int:
    """返回完成标记发现窗口：采集周期 + 24h 恢复 + Gate/落库缓冲。"""
    cycle_seconds = 0
    if is_interval and cycle_value_type == "cycle":
        try:
            cycle_minutes = int(cycle_value)
        except (TypeError, ValueError):
            cycle_minutes = 0
        if cycle_minutes > 0:
            cycle_seconds = cycle_minutes * 60
    return cycle_seconds + ROUND_RECOVERY_SECONDS + ROUND_GATE_INTERVAL_SECONDS + ROUND_MARKER_BUFFER_SECONDS


def cap_completed_round_lookback_seconds(
    requested_seconds: int,
    *,
    retention_seconds: int = VM_RETENTION_SECONDS,
) -> tuple[int, bool]:
    """按 VM retention 限制标记窗口，并返回是否发生截断。"""
    requested = max(1, int(requested_seconds))
    retention = max(1, int(retention_seconds))
    return min(requested, retention), requested > retention


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


def query_latest_completed_rounds(
    instance_ids: list[str] | tuple[str, ...],
    *,
    lookback_seconds: int,
    collection: Collection | None = None,
    collection_role: str | None = None,
    minimum_completed_at_by_instance: dict[str, float] | None = None,
) -> dict[str, CompletedRound]:
    """用一对 VM 查询批量取得各任务的最新完整轮次。"""
    normalized_ids = list(dict.fromkeys(str(value) for value in instance_ids if value not in (None, "")))
    if not normalized_ids:
        return {}
    coll = collection or Collection()
    instance_pattern = "|".join(re.escape(value) for value in normalized_ids)
    matchers = [f"instance_id=~'^({instance_pattern})$'"]
    if collection_role is not None:
        matchers.append(f"collection_role='{collection_role}'")
    sql = f"{ROUND_COMPLETE_METRIC}{{{','.join(matchers)}}}"
    # 两次 instant query 固定在同一评估时刻，避免跨轮次拼出旧 T + 新 C。
    evaluation_time = time.time()
    value_payload = coll.query(
        sql,
        lookback_seconds=lookback_seconds,
        evaluation_time=evaluation_time,
        timeout=ROUND_MARKER_QUERY_TIMEOUT_SECONDS,
        retries=ROUND_MARKER_QUERY_RETRIES,
    )
    timestamp_payload = coll.query_sample_timestamps(
        sql,
        lookback_seconds=lookback_seconds,
        evaluation_time=evaluation_time,
        timeout=ROUND_MARKER_QUERY_TIMEOUT_SECONDS,
        retries=ROUND_MARKER_QUERY_RETRIES,
    )

    timestamp_rows = ((timestamp_payload or {}).get("data") or {}).get("result") or []
    completed_at_by_metric = {}
    for row in timestamp_rows:
        key = Collection.metric_key(row)
        value = (row.get("value") or [None, None])[1] if isinstance(row, dict) else None
        try:
            completed_at = float(value)
        except (TypeError, ValueError):
            continue
        if key is not None:
            completed_at_by_metric[key] = completed_at

    best_by_instance: dict[str, CompletedRound] = {}
    value_rows = ((value_payload or {}).get("data") or {}).get("result") or []
    for row in value_rows:
        key = Collection.metric_key(row)
        metric = row.get("metric") if isinstance(row, dict) else None
        instance_id = metric.get("instance_id") if isinstance(metric, dict) else None
        if instance_id not in normalized_ids:
            continue
        value = (row.get("value") or [None, None])[1] if isinstance(row, dict) else None
        try:
            started_at = int(float(value))
        except (TypeError, ValueError):
            continue
        completed_at = completed_at_by_metric.get(key)
        if completed_at is None or completed_at < started_at:
            continue
        minimum_completed_at = (minimum_completed_at_by_instance or {}).get(instance_id)
        if minimum_completed_at is not None and completed_at < minimum_completed_at:
            continue
        candidate = CompletedRound(
            started_at=started_at,
            completed_at=completed_at,
            labels={str(label): str(label_value) for label, label_value in metric.items()},
        )
        best = best_by_instance.get(instance_id)
        candidate_order = (
            candidate.started_at,
            candidate.snapshot_complete,
            candidate.completed_at,
        )
        best_order = (
            (
                best.started_at,
                best.snapshot_complete,
                best.completed_at,
            )
            if best is not None
            else None
        )
        if best_order is None or candidate_order > best_order:
            best_by_instance[instance_id] = candidate
    return best_by_instance


def query_latest_completed_round(
    instance_id: str,
    *,
    lookback_seconds: int,
    collection: Collection | None = None,
    collection_role: str | None = None,
) -> CompletedRound | None:
    """单任务兼容入口；Gate 使用批量入口避免任务维度查询放大。"""
    return query_latest_completed_rounds(
        [instance_id],
        lookback_seconds=lookback_seconds,
        collection=collection,
        collection_role=collection_role,
    ).get(instance_id)


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
        payload = coll.query(
            sql,
            timeout=ROUND_MARKER_QUERY_TIMEOUT_SECONDS,
            retries=ROUND_MARKER_QUERY_RETRIES,
        )
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
        payload = coll.query(
            sql,
            timeout=ROUND_MARKER_QUERY_TIMEOUT_SECONDS,
            retries=ROUND_MARKER_QUERY_RETRIES,
        )
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


def query_instance_ids_with_vm_data(
    instance_ids: list[str] | tuple[str, ...],
    *,
    collection: Collection | None = None,
) -> set[str]:
    """批量探测兼容任务在默认查询窗口内是否存在数据。"""
    normalized_ids = list(dict.fromkeys(str(value) for value in instance_ids if value not in (None, "")))
    if not normalized_ids:
        return set()
    instance_pattern = "|".join(re.escape(value) for value in normalized_ids)
    sql = f"count by (instance_id) ({{instance_id=~'^({instance_pattern})$'}})"
    payload = (collection or Collection()).query(
        sql,
        timeout=ROUND_MARKER_QUERY_TIMEOUT_SECONDS,
        retries=ROUND_MARKER_QUERY_RETRIES,
    )
    rows = ((payload or {}).get("data") or {}).get("result") or []
    matched = set()
    for row in rows:
        metric = row.get("metric") if isinstance(row, dict) else None
        instance_id = metric.get("instance_id") if isinstance(metric, dict) else None
        if instance_id in normalized_ids:
            matched.add(instance_id)
    return matched


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
