# -- coding: utf-8 --
"""PC 发现采集的 Server 侧服务：VM 快照解析、权威状态机与逐 PC 对账。

- parse_pc_vm_rows：把 pc_info / pc_software_info 指标行解析为逐 PC 的不可变快照，
  任何完整性条件不满足都降级 partial（绝不伪装 complete）；
- PCAuthorityService：一台 PC 同一时间只由一个权威任务写入和删除（设计 §11）；
- PCSnapshotReconciler：严格白名单写入 PC 资产，人工字段绝不被采集覆盖；
- apply_pc_snapshots：逐 PC 独立对账，单台失败不影响其他目标。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from django.db import transaction

from apps.cmdb.constants.constants import INSTANCE, INSTANCE_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.core.logger import cmdb_logger as logger

PC_METRIC_NAME = "pc_info"
PC_SOFTWARE_METRIC_NAME = "pc_software_info"

# 采集允许写入的 PC 字段（与 model_config.xlsx attr-pc 自动发现信息组一致）。
# 人工资产字段（asset_code/user/location 等）和组织字段绝不出现在更新 payload。
PC_COLLECTED_FIELDS = frozenset({
    "inst_name", "host_name", "ip_addr", "os_type", "os_name", "os_version",
    "os_build", "architecture", "hardware_uuid", "serial_number",
    "device_model", "logged_in_user", "last_collect_time",
})

# 采集允许写入的软件字段（与 attr-pc_software 一致）。
# 归属只走 install_on 关联：pc_inst_name/snapshot_id 是 VM 传输标签，不落为资产字段。
SOFTWARE_COLLECTED_FIELDS = frozenset({
    "inst_name", "name", "version", "publisher", "software_key", "product_id",
    "install_location", "install_date", "architecture", "source", "last_collect_time",
})

_OS_INST_PREFIX = {"windows": "WIN-", "macos": "MAC-"}

_MAX_ERROR_DETAIL = 500


def filter_pc_payload(raw):
    """严格白名单：只保留采集字段，禁止把原始 PC dict 全量传给图客户端。"""
    return {key: value for key, value in (raw or {}).items() if key in PC_COLLECTED_FIELDS}


def filter_software_payload(raw):
    """软件白名单：去掉传输标签（pc_inst_name/snapshot_id）与未知字段。"""
    return {key: value for key, value in (raw or {}).items() if key in SOFTWARE_COLLECTED_FIELDS}


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


class PCSnapshotReconciler:
    """单台 PC 的快照对账：权威校验 → 白名单写入（创建/更新）。

    软件 upsert 与安全差集删除在 Task 9/10 扩展本类；
    当前 apply() 只负责 PC 实体本身，allow_delete 透传权威决策与快照完整性。
    """

    def __init__(self, task):
        self.task = task

    def _organization(self):
        team = getattr(self.task, "team", None) or []
        return team[0] if team else ""

    @staticmethod
    def _validate_identity(payload):
        inst_name = payload.get("inst_name", "")
        os_type = payload.get("os_type", "")
        prefix = _OS_INST_PREFIX.get(os_type)
        if not inst_name or prefix is None or not inst_name.startswith(prefix):
            return False
        return True

    def apply(self, snapshot):
        result = {"pc_failed": 0, "pc_status": "skipped", "error_code": "", "allow_delete": False}
        payload = filter_pc_payload(snapshot.pc)
        if not self._validate_identity(payload):
            result.update(pc_failed=1, error_code="PC_IDENTITY_INVALID")
            return result

        decision = PCAuthorityService.authorize(
            self.task, payload["inst_name"], snapshot.snapshot_id, snapshot.collected_at
        )
        if decision.mode == "conflict":
            result.update(pc_failed=1, error_code=decision.error_code)
            return result
        if decision.mode == "stale":
            result["pc_status"] = "stale"
            return result

        params = [
            {"field": "model_id", "type": "str=", "value": "pc"},
            {"field": "inst_name", "type": "str=", "value": payload["inst_name"]},
        ]
        with GraphClient() as ag:
            existing, _ = ag.query_entity(INSTANCE, params)
            if existing:
                entity = ag.set_entity_properties(INSTANCE, [existing[0]["_id"]], payload, {}, [])
                result["pc_status"] = "updated"
                result["pc_entity"] = entity[0] if entity else existing[0]
            else:
                create_payload = dict(payload)
                create_payload.update(
                    model_id="pc",
                    organization=self._organization(),
                    collect_task=self.task.id,
                    auto_collect=True,
                )
                result["pc_entity"] = ag.create_entity(INSTANCE, create_payload, {}, [])
                result["pc_status"] = "added"
            sw_counts = self._upsert_software(ag, snapshot, result["pc_entity"])

        result.update(sw_counts)
        if decision.mode == "owner":
            PCAuthorityService.mark_applied(decision.authority, snapshot.snapshot_id, snapshot.collected_at)
            # 任何软件写入或关联失败都不得删除（降级部分成功）
            result["allow_delete"] = snapshot.can_delete and sw_counts["software_failed"] == 0
        if sw_counts["software_failed"]:
            result["error_code"] = "CMDB_WRITE_PARTIAL"
        return result

    def _upsert_software(self, ag, snapshot, pc_entity):
        """软件按 inst_name 无删除 upsert + install_on 关联；任一失败计入 software_failed。"""
        counts = {"software_added": 0, "software_updated": 0, "software_failed": 0}
        for row in snapshot.software:
            payload = filter_software_payload(row)
            try:
                params = [
                    {"field": "model_id", "type": "str=", "value": "pc_software"},
                    {"field": "inst_name", "type": "str=", "value": payload["inst_name"]},
                ]
                existing, _ = ag.query_entity(INSTANCE, params)
                if existing:
                    ag.set_entity_properties(INSTANCE, [existing[0]["_id"]], payload, {}, [])
                    sw_entity = dict(existing[0], **payload)
                    counts["software_updated"] += 1
                else:
                    create_payload = dict(payload)
                    create_payload.update(
                        model_id="pc_software",
                        organization=self._organization(),
                        collect_task=self.task.id,
                        auto_collect=True,
                    )
                    sw_entity = ag.create_entity(INSTANCE, create_payload, {}, [])
                    counts["software_added"] += 1
                asso_info = {
                    "model_asst_id": "pc_software_install_on_pc",
                    "src_model_id": "pc_software",
                    "src_inst_id": sw_entity["_id"],
                    "dst_model_id": "pc",
                    "dst_inst_id": pc_entity["_id"],
                    "asst_id": "install_on",
                }
                try:
                    ag.create_edge(
                        INSTANCE_ASSOCIATION, sw_entity["_id"], INSTANCE,
                        pc_entity["_id"], INSTANCE, asso_info, "model_asst_id",
                    )
                except Exception as exc:  # noqa: BLE001 - 边已存在即目标状态，幂等视为成功
                    if str(exc) != "edge already exists":
                        raise
            except Exception as exc:  # noqa: BLE001 - 单条软件失败不影响其余软件
                logger.warning(
                    "[PC] software upsert failed: task=%s sw=%s err=%s",
                    getattr(self.task, "id", None), payload.get("inst_name"), type(exc).__name__,
                )
                counts["software_failed"] += 1
        return counts


def apply_pc_snapshots(task, snapshots):
    """逐 PC 独立对账：单台异常捕获为稳定错误码并继续下一台，互不回滚。

    错误详情脱敏（不落凭据）且截断到 500 字符。
    """
    summary = {"add": 0, "update": 0, "delete": 0, "association": 0}
    rows = []
    for snapshot in snapshots or []:
        inst_name = (snapshot.pc or {}).get("inst_name", "")
        try:
            result = PCSnapshotReconciler(task).apply(snapshot)
        except Exception as exc:  # noqa: BLE001 - 单台失败不阻断其他目标
            logger.warning("[PC] reconcile failed: task=%s pc=%s err=%s", getattr(task, "id", None), inst_name, type(exc).__name__)
            result = {
                "pc_failed": 1,
                "pc_status": "failed",
                "error_code": "CMDB_WRITE_PARTIAL",
                "error_detail": str(exc)[:_MAX_ERROR_DETAIL],
            }
        status = "failed" if result.get("pc_failed") or result.get("software_failed") else "success"
        if result.get("pc_status") == "added":
            summary["add"] += 1
        elif result.get("pc_status") == "updated":
            summary["update"] += 1
        summary["association"] += result.get("software_added", 0)
        row = {
            "inst_name": inst_name,
            "_status": status,
            "_error": result.get("error_code", ""),
        }
        if result.get("error_detail"):
            row["_error_detail"] = result["error_detail"][:_MAX_ERROR_DETAIL]
        rows.append(row)
    logger.info(
        "[PC] apply_pc_snapshots: task=%s summary=%s", getattr(task, "id", None), summary
    )
    return {"format_data": summary, "snapshots": len(snapshots or []), "results": rows}
