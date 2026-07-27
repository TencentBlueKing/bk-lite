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
