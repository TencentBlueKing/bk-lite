# -- coding: utf-8 --
"""PC 发现采集的 Server 侧服务：VM 快照解析、安全门与逐 PC 对账入口。

本模块按 Task 6~10 逐步填充：
- parse_pc_vm_rows：把 pc_info / pc_software_info 指标行解析为逐 PC 的不可变快照，
  任何完整性条件不满足都降级 partial（绝不伪装 complete）；
- apply_pc_snapshots：逐 PC 对账入口（白名单写入、软件 upsert、安全差集删除
  分别在 Task 8/9/10 落地），当前只产出任务摘要骨架。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from django.db import transaction

from apps.core.logger import cmdb_logger as logger

PC_METRIC_NAME = "pc_info"
PC_SOFTWARE_METRIC_NAME = "pc_software_info"


@dataclass(frozen=True)
class PCSnapshot:
    pc: dict
    software: tuple
    status: str
    snapshot_id: str
    expected_count: int
    error_count: int
    collected_at: datetime
    error_code: str = ""

    @property
    def can_delete(self) -> bool:
        return self.status == "complete" and self.error_count == 0 and len(self.software) == self.expected_count


def _to_int(raw, default=0):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _metric_time(row):
    ts = row.get("_metric_time")
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _build_snapshot(pc_row, software_rows):
    expected_count = _to_int(pc_row.get("software_expected_count"))
    error_count = _to_int(pc_row.get("software_error_count"))
    status = pc_row.get("software_snapshot_status", "partial")
    snapshot_id = pc_row.get("snapshot_id", "")
    inst_name = pc_row.get("inst_name", "")

    error_code = ""
    owned_rows = [row for row in software_rows if row.get("pc_inst_name") == inst_name and row.get("snapshot_id") == snapshot_id]

    seen_inst_names = set()
    duplicated = False
    for row in owned_rows:
        sw_inst = row.get("inst_name", "")
        if sw_inst in seen_inst_names:
            duplicated = True
            break
        seen_inst_names.add(sw_inst)

    if status != "complete":
        error_code = "SOFTWARE_PARTIAL"
        status = "partial"
    elif error_count != 0:
        error_code = "SOFTWARE_PARTIAL"
        status = "partial"
    elif duplicated or len(owned_rows) != expected_count:
        error_code = "SNAPSHOT_COUNT_MISMATCH"
        status = "partial"

    collected_at = max([_metric_time(pc_row), *[_metric_time(row) for row in owned_rows]])
    return PCSnapshot(
        pc=dict(pc_row),
        software=tuple(dict(row) for row in owned_rows),
        status=status,
        snapshot_id=snapshot_id,
        expected_count=expected_count,
        error_count=error_count,
        collected_at=collected_at,
        error_code=error_code,
    )


def parse_pc_vm_rows(rows):
    """把 pc_info / pc_software_info 的 VM label 行解析为逐 PC 快照列表。

    安全门：计数一致、错误计数为零、软件归属当前 PC、快照 ID 一致、无重复实例名；
    任一不满足都降级 partial。同一 PC 多轮快照只保留指标时间最新的一轮。
    """
    pc_rows = {}
    software_rows = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("__name__") == PC_METRIC_NAME or row.get("bk_obj_id") == "pc":
            key = (row.get("inst_name", ""), row.get("snapshot_id", ""))
            pc_rows.setdefault(key, row)
        elif row.get("__name__") == PC_SOFTWARE_METRIC_NAME or row.get("bk_obj_id") == "pc_software":
            key = (row.get("pc_inst_name", ""), row.get("snapshot_id", ""))
            software_rows.setdefault(key, []).append(row)

    snapshots_by_pc = {}
    for key, pc_row in pc_rows.items():
        inst_name = pc_row.get("inst_name", "")
        snapshot = _build_snapshot(pc_row, software_rows.get(key, []))
        existing = snapshots_by_pc.get(inst_name)
        if existing is None or snapshot.collected_at > existing.collected_at:
            snapshots_by_pc[inst_name] = snapshot
    return list(snapshots_by_pc.values())


@dataclass(frozen=True)
class PCAuthorityDecision:
    """authorize() 的结论：mode 决定本任务对该 PC 的写/删权限。"""

    mode: str  # owner / conflict / pending_handover / stale
    allow_delete: bool
    error_code: str = ""
    authority: object = None


class PCAuthorityService:
    """PC 权威采集任务状态机（设计 §11）。

    - 首个识别 inst_name 的任务绑定为权威任务（唯一约束解决并发首绑）；
    - 其他任务命中返回 conflict(SOURCE_TASK_CONFLICT)，不读写；
    - 待移交任务可写新增/更新但 allow_delete=False，
      只有完整快照落地后 complete_handover 才切换权威并清空 pending；
    - 旧于或等于最近已应用时间的快照按幂等忽略（stale）。
    所有写路径都在 transaction.atomic + select_for_update 内完成。
    """

    @staticmethod
    def authorize(task, pc_inst_name, snapshot_id, collected_at):
        from apps.cmdb.models.pc_discovery import PCDiscoveryAuthority

        with transaction.atomic():
            authority, created = PCDiscoveryAuthority.objects.select_for_update().get_or_create(
                pc_inst_name=pc_inst_name,
                defaults={"authoritative_task": task},
            )
            if created:
                return PCAuthorityDecision(mode="owner", allow_delete=True, authority=authority)
            if authority.authoritative_task_id == task.id:
                if authority.last_snapshot_time is not None and collected_at <= authority.last_snapshot_time:
                    return PCAuthorityDecision(mode="stale", allow_delete=False, authority=authority)
                return PCAuthorityDecision(mode="owner", allow_delete=True, authority=authority)
            if authority.pending_task_id == task.id:
                return PCAuthorityDecision(mode="pending_handover", allow_delete=False, authority=authority)
            return PCAuthorityDecision(
                mode="conflict",
                allow_delete=False,
                error_code="SOURCE_TASK_CONFLICT",
                authority=authority,
            )

    @staticmethod
    def request_handover(pc_inst_name, new_task):
        """管理员授权新任务接管；authority 不存在时抛 DoesNotExist。"""
        from apps.cmdb.models.pc_discovery import PCDiscoveryAuthority

        with transaction.atomic():
            authority = PCDiscoveryAuthority.objects.select_for_update().get(pc_inst_name=pc_inst_name)
            if authority.authoritative_task_id != new_task.id:
                authority.pending_task = new_task
                authority.save(update_fields=["pending_task", "updated_at"])
            return authority

    @staticmethod
    def complete_handover(authority, task, snapshot_status):
        """完整快照落地后切换权威；部分快照或非待移交任务一律不切换。"""
        if snapshot_status != "complete":
            return False
        with transaction.atomic():
            locked = type(authority).objects.select_for_update().get(pk=authority.pk)
            if locked.pending_task_id != task.id:
                return False
            locked.authoritative_task = task
            locked.pending_task = None
            locked.save(update_fields=["authoritative_task", "pending_task", "updated_at"])
        authority.refresh_from_db()
        return True

    @staticmethod
    def mark_applied(authority, snapshot_id, collected_at):
        """快照完整应用后记录最近应用水位，供 stale 判定。"""
        authority.last_snapshot_id = snapshot_id
        authority.last_snapshot_time = collected_at
        authority.save(update_fields=["last_snapshot_id", "last_snapshot_time", "updated_at"])


def apply_pc_snapshots(task, snapshots):
    """逐 PC 对账入口。

    Task 8/9/10 将在此落地白名单写入、软件 upsert 与安全差集删除；
    当前返回空摘要，保证任务详情链路可用且不触碰 CMDB 数据。
    """
    summary = {"add": 0, "update": 0, "delete": 0, "association": 0}
    logger.info(
        "[PC] apply_pc_snapshots skeleton: task=%s snapshots=%s",
        getattr(task, "id", None),
        [f"{snap.pc.get('inst_name')}:{snap.status}" for snap in snapshots or []],
    )
    return {"format_data": summary, "snapshots": len(snapshots or [])}
