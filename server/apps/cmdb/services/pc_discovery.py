# -- coding: utf-8 --
"""PC 发现采集的 Server 侧服务：VM 快照解析与逐 PC 对账。

- parse_pc_vm_rows：把 pc_info_gauge / pc_software_info_gauge 指标行解析为逐 PC 的不可变快照，
  任何完整性条件不满足都降级 partial（绝不伪装 complete）；
- PCSnapshotReconciler：严格白名单写入 PC 资产，人工字段绝不被采集覆盖；
- apply_pc_snapshots：逐 PC 独立对账，单台失败不影响其他目标。
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from apps.cmdb.collection.cleanup import cleanup_due
from apps.cmdb.collection.round_metadata import RoundMetadataProtocolError, build_round_metadata_lookups
from apps.cmdb.constants.constants import INSTANCE, INSTANCE_ASSOCIATION, OPERATOR_INSTANCE, DataCleanupStrategy
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.change_record import COLLECT_AUTOMATION_CHANGE, DELETE_INST
from apps.cmdb.services.instance_identity import prepare_new_instance_identity
from apps.cmdb.utils.change_record import batch_create_change_record
from apps.core.logger import cmdb_logger as logger

# VictoriaMetrics 按 Influx 测量名 + 字段名 gauge 落库，序列名带 _gauge。
# 查询必须用落库名；解析仍接受未加后缀的旧名。
PC_METRIC_NAME = "pc_info_gauge"
PC_SOFTWARE_METRIC_NAME = "pc_software_info_gauge"
PC_QUERY_METRIC_NAMES = {
    "pc_info": PC_METRIC_NAME,
    "pc_software_info": PC_SOFTWARE_METRIC_NAME,
}
_PC_METRIC_NAMES = frozenset({PC_METRIC_NAME, "pc_info"})
_PC_SOFTWARE_METRIC_NAMES = frozenset({PC_SOFTWARE_METRIC_NAME, "pc_software_info"})


def vm_query_metric_name(name: str) -> str:
    """把逻辑指标名换成 VictoriaMetrics 中的序列名。"""
    return PC_QUERY_METRIC_NAMES.get(name, name)


def pc_metric_aliases(names) -> dict:
    """逻辑指标名和 VM 序列名共用同一个分桶，避免插件只认其中一边。"""
    buckets = {}
    for name in names:
        bucket = buckets.setdefault(name, [])
        vm_name = vm_query_metric_name(name)
        if vm_name != name:
            buckets[vm_name] = bucket
    return buckets


# 采集允许写入的 PC 字段（与 model_config.xlsx attr-pc 自动发现信息组一致）。
# 人工资产字段（asset_code/user/location 等）和组织字段绝不出现在更新 payload。
PC_COLLECTED_FIELDS = frozenset(
    {
        "inst_name",
        "host_name",
        "ip_addr",
        "os_type",
        "os_name",
        "os_version",
        "os_build",
        "architecture",
        "hardware_uuid",
        "serial_number",
        "brand",
        "device_model",
        "cpu",
        "men",
        "disk",
        "logged_in_user",
        "last_collect_time",
    }
)

# 采集允许写入的软件字段（与 attr-pc_software 一致）。
# 归属只走 install_on 关联：pc_inst_name 是稳定传输标签，snapshot_id 只存在轮次元数据中。
SOFTWARE_COLLECTED_FIELDS = frozenset(
    {
        "inst_name",
        "name",
        "version",
        "publisher",
        "software_key",
        "product_id",
        "install_location",
        "install_date",
        "architecture",
        "source",
        "last_collect_time",
    }
)

_OS_INST_PREFIX = {"windows": "WIN-", "macos": "MAC-"}

_MAX_ERROR_DETAIL = 500
_SOFTWARE_IDENTITY_BATCH_SIZE = 100
_BYTES_PER_GB = 1024**3
# 大于等于 1MiB 的容量仍是采集器上报的字节；已经换算成 GB 的数值远小于这个门槛。
_BYTE_CAPACITY_FLOOR = 1024**2
_CAPACITY_FIELDS = ("men", "disk")


def capacity_as_gb(value):
    """把内存、硬盘容量收成 GB 字符串。空值保持空，无法解析的原文保持原文。"""
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    if number >= _BYTE_CAPACITY_FLOOR:
        number = number / _BYTES_PER_GB
    rounded = round(number, 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"


def _write_check_map(payload):
    """更新时只放行本次要写的字段，避免空的可编辑清单把属性全部滤掉。"""
    return {"editable": {key: key for key in payload}}


def filter_pc_payload(raw):
    """严格白名单：只保留采集字段，禁止把原始 PC dict 全量传给图客户端。"""
    payload = {key: value for key, value in (raw or {}).items() if key in PC_COLLECTED_FIELDS}
    for key in _CAPACITY_FIELDS:
        if key in payload:
            payload[key] = capacity_as_gb(payload[key])
    return payload


def filter_software_payload(raw):
    """软件白名单：去掉关联用的 pc_inst_name 与未知字段。"""
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


def _metric_timestamp_ms(row):
    try:
        return int(round(float(row.get("_metric_time")) * 1000))
    except (TypeError, ValueError, OSError) as exc:
        raise RoundMetadataProtocolError("invalid_publish_timestamp") from exc


def _build_snapshot(pc_row, software_rows, metadata):
    details = metadata.get("details") or {}
    expected_count = _to_int(details.get("software_expected_count"))
    error_count = _to_int(details.get("software_error_count"))
    status = metadata.get("snapshot_status", "partial")
    snapshot_id = metadata.get("snapshot_id", "")
    inst_name = pc_row.get("inst_name", "")

    error_code = ""
    owned_rows = [row for row in software_rows if row.get("pc_inst_name") == inst_name]

    seen_inst_names = set()
    seen_software_keys = set()
    duplicated = False
    for row in owned_rows:
        sw_inst = row.get("inst_name", "")
        software_key = row.get("software_key", "")
        if not sw_inst or not software_key or sw_inst in seen_inst_names or software_key in seen_software_keys:
            duplicated = True
            break
        seen_inst_names.add(sw_inst)
        seen_software_keys.add(software_key)

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


def _partial_round_metadata():
    """没有完成标记时仍收下已上报的 PC，但禁止差集删除。"""
    return {"snapshot_status": "partial", "snapshot_id": "", "details": {}}


def parse_pc_vm_rows(rows, metadata_by_round):
    """把 pc_info_gauge / pc_software_info_gauge 的 VM label 行解析为逐 PC 快照列表。

    安全门：计数一致、错误计数为零、软件归属当前 PC、轮次元数据完整、无重复身份；
    任一不满足都降级 partial。同一 PC 多轮快照只保留指标时间最新的一轮。
    批量里部分目标失败时没有完成标记，已上报的目标仍生成 partial 快照。
    """
    if not isinstance(metadata_by_round, dict):
        raise RoundMetadataProtocolError("metadata_missing")
    pc_rows = {}
    software_rows = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("__name__") in _PC_METRIC_NAMES or row.get("bk_obj_id") == "pc":
            round_key = (row.get("collection_target", ""), _metric_timestamp_ms(row))
            key = (*round_key, row.get("inst_name", ""))
            if key in pc_rows:
                raise RoundMetadataProtocolError("duplicate_pc_root")
            pc_rows[key] = row
        elif row.get("__name__") in _PC_SOFTWARE_METRIC_NAMES or row.get("bk_obj_id") == "pc_software":
            key = (
                row.get("collection_target", ""),
                _metric_timestamp_ms(row),
                row.get("pc_inst_name", ""),
            )
            software_rows.setdefault(key, []).append(row)

    snapshots_by_pc = {}
    for key, pc_row in pc_rows.items():
        inst_name = pc_row.get("inst_name", "")
        round_key = key[:2]
        metadata = metadata_by_round.get(round_key) or _partial_round_metadata()
        snapshot = _build_snapshot(pc_row, software_rows.get(key, []), metadata)
        existing = snapshots_by_pc.get(inst_name)
        if existing is None or snapshot.collected_at > existing.collected_at:
            snapshots_by_pc[inst_name] = snapshot
    return list(snapshots_by_pc.values())


class PCSnapshotReconciler:
    """单台 PC 的快照对账：白名单写入、软件 upsert 与安全差集删除。"""

    def __init__(self, task):
        self.task = task

    def _organization(self):
        """实例 organization 是组织 ID 数组。任务 team 已是数组，标量也收成一项。"""
        team = getattr(self.task, "team", None) or []
        if isinstance(team, (str, bytes)) or not isinstance(team, (list, tuple)):
            return [] if team in (None, "") else [team]
        return [item for item in team if item not in (None, "")]

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

        params = [
            {"field": "model_id", "type": "str=", "value": "pc"},
            {"field": "inst_name", "type": "str=", "value": payload["inst_name"]},
        ]
        collect_time = snapshot.collected_at.isoformat()
        payload["last_collect_time"] = collect_time
        runtime = {"collect_time": collect_time}
        with GraphClient() as ag:
            existing, _ = ag.query_entity(INSTANCE, params)
            if existing:
                update_payload = dict(payload, **runtime)
                entity = ag.set_entity_properties(INSTANCE, [existing[0]["_id"]], update_payload, _write_check_map(update_payload), [])
                result["pc_status"] = "updated"
                result["pc_entity"] = entity[0] if entity else existing[0]
            else:
                create_payload = dict(payload)
                create_payload.update(
                    model_id="pc",
                    organization=self._organization(),
                    collect_task=self.task.id,
                    auto_collect=True,
                    **runtime,
                )
                create_payload = prepare_new_instance_identity(create_payload)
                result["pc_entity"] = ag.create_entity(INSTANCE, create_payload, {}, [])
                result["pc_status"] = "added"
            sw_counts = self._upsert_software(ag, snapshot, result["pc_entity"])

        result.update(sw_counts)
        allow_delete = snapshot.can_delete and sw_counts["software_failed"] == 0
        delete_counts = {"software_deleted": 0, "delete_failed": 0}
        allow_delete = allow_delete and str(result["pc_entity"].get("collect_task")) == str(self.task.id)
        if allow_delete and self.task.data_cleanup_strategy != DataCleanupStrategy.NO_CLEANUP:
            with GraphClient() as ag:
                delete_counts = self._delete_missing_software(ag, snapshot, result["pc_entity"])
        result.update(delete_counts)
        result["allow_delete"] = allow_delete
        if sw_counts["software_failed"] or delete_counts["delete_failed"]:
            result["error_code"] = "CMDB_WRITE_PARTIAL"
        return result

    def _delete_missing_software(self, ag, snapshot, pc_entity):
        """当前 PC 关联集合的差集删除：只删该 PC install_on 下、不在快照中的软件。

        绝不查询整个 pc_software 模型作为差集。删除成功的实体写 DELETE_INST 审计。
        """
        counts = {"software_deleted": 0, "delete_failed": 0, "deleted_names": [], "failed_names": []}
        edges = ag.query_edge(
            INSTANCE_ASSOCIATION,
            [
                {"field": "dst_inst_id", "type": "int=", "value": pc_entity["_id"]},
                {"field": "asst_id", "type": "str=", "value": "install_on"},
                {"field": "model_asst_id", "type": "str=", "value": "pc_software_install_on_pc"},
            ],
        )
        keep_inst_names = {row.get("inst_name") for row in snapshot.software}
        id_to_entity = {}
        deleted_entities = []
        for edge in edges:
            src_id = edge.get("src_inst_id")
            entity = id_to_entity.get(src_id)
            if entity is None:
                items, _ = ag.query_entity(
                    INSTANCE,
                    [
                        {"field": "model_id", "type": "str=", "value": "pc_software"},
                        {"field": "_id", "type": "id=", "value": src_id},
                    ],
                )
                entity = items[0] if items else None
                id_to_entity[src_id] = entity
            if entity is None or entity.get("inst_name") in keep_inst_names:
                continue
            if not cleanup_due(self.task.data_cleanup_strategy, entity.get("collect_time"), snapshot.collected_at.isoformat(), self.task.expire_days):
                continue
            try:
                if not ag.delete_entity_if_unchanged(INSTANCE, entity):
                    continue
                deleted_entities.append(entity)
                counts["software_deleted"] += 1
                counts["deleted_names"].append(entity.get("inst_name", ""))
            except Exception as exc:  # noqa: BLE001 - 单条删除失败保留实体，下轮重试
                logger.warning(
                    "[PC] software delete failed: task=%s sw=%s err=%s",
                    getattr(self.task, "id", None),
                    entity.get("inst_name"),
                    type(exc).__name__,
                )
                counts["delete_failed"] += 1
                counts["failed_names"].append(entity.get("inst_name", ""))
        if deleted_entities:
            self._write_delete_audit(deleted_entities, snapshot.snapshot_id)
        return counts

    def _write_delete_audit(self, deleted_entities, snapshot_id):
        records = [
            {
                "inst_id": entity["_id"],
                "model_id": entity.get("model_id", "pc_software"),
                "before_data": entity,
                "model_object": OPERATOR_INSTANCE,
                "message": (
                    f"自动采集删除实例. 模型:{entity.get('model_id', 'pc_software')} " f"实例:{entity.get('inst_name')} 任务:{self.task.id} 快照:{snapshot_id}"
                ),
            }
            for entity in deleted_entities
        ]
        batch_create_change_record(
            INSTANCE,
            DELETE_INST,
            records,
            operator="system",
            scenario=COLLECT_AUTOMATION_CHANGE,
        )

    def _software_identity_index(self, ag, snapshot):
        """按 inst_name 分块读取已有软件。同名只留返回列表的第一条；没有名称时不查询。"""
        names = []
        seen = set()
        for row in snapshot.software:
            name = row.get("inst_name") if isinstance(row, dict) else None
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        index = {}
        for start in range(0, len(names), _SOFTWARE_IDENTITY_BATCH_SIZE):
            chunk = names[start : start + _SOFTWARE_IDENTITY_BATCH_SIZE]
            rows = ag.query_entity_by_inst_names(chunk, model_id="pc_software") or []
            for entity in rows:
                if not isinstance(entity, dict):
                    continue
                inst_name = entity.get("inst_name")
                if not inst_name or inst_name in index:
                    continue
                index[inst_name] = entity
        return index

    def _upsert_software(self, ag, snapshot, pc_entity):
        """软件按 inst_name 无删除 upsert + install_on 关联；身份按固定块读取，任一失败计入 software_failed。"""
        counts = {"software_added": 0, "software_updated": 0, "software_failed": 0, "outcomes": []}
        collect_time = snapshot.collected_at.isoformat()
        identity_index = self._software_identity_index(ag, snapshot)
        for row in snapshot.software:
            payload = filter_software_payload(row)
            payload["last_collect_time"] = collect_time
            sw_entity = None
            created_this_round = False
            try:
                existing = identity_index.get(payload["inst_name"])
                if existing:
                    update_payload = dict(payload, collect_time=collect_time)
                    ag.set_entity_properties(INSTANCE, [existing["_id"]], update_payload, _write_check_map(update_payload), [])
                    sw_entity = dict(existing, **payload)
                    outcome_key = "software_updated"
                else:
                    create_payload = dict(payload)
                    create_payload.update(
                        model_id="pc_software",
                        organization=self._organization(),
                        collect_task=self.task.id,
                        auto_collect=True,
                        collect_time=collect_time,
                    )
                    create_payload = prepare_new_instance_identity(create_payload)
                    sw_entity = ag.create_entity(INSTANCE, create_payload, {}, [])
                    created_this_round = True
                    identity_index[payload["inst_name"]] = sw_entity
                    outcome_key = "software_added"
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
                        INSTANCE_ASSOCIATION,
                        sw_entity["_id"],
                        INSTANCE,
                        pc_entity["_id"],
                        INSTANCE,
                        asso_info,
                        "model_asst_id",
                    )
                except Exception as exc:  # noqa: BLE001 - 边已存在即目标状态，幂等视为成功
                    if str(exc) != "edge already exists":
                        raise
                counts[outcome_key] += 1
                counts["outcomes"].append((payload["inst_name"], "success"))
            except Exception as exc:  # noqa: BLE001 - 单条软件失败不影响其余软件
                if created_this_round and sw_entity:
                    try:
                        ag.detach_delete_entity(INSTANCE, sw_entity["_id"])
                        identity_index.pop(payload.get("inst_name"), None)
                    except Exception as cleanup_exc:  # noqa: BLE001 - 补偿失败保留，下轮继续治理
                        logger.warning(
                            "[PC] orphan software compensation failed: task=%s sw=%s err=%s",
                            getattr(self.task, "id", None),
                            payload.get("inst_name"),
                            type(cleanup_exc).__name__,
                        )
                logger.warning(
                    "[PC] software upsert failed: task=%s sw=%s err=%s",
                    getattr(self.task, "id", None),
                    payload.get("inst_name"),
                    type(exc).__name__,
                )
                counts["software_failed"] += 1
                counts["outcomes"].append((payload.get("inst_name", ""), "failed"))
        return counts


def apply_pc_snapshots(task, snapshots):
    """逐 PC 独立对账：单台异常捕获为稳定错误码并继续下一台，互不回滚。

    format_data 为 IPAM 同款行列表（add/update/delete/association + all），
    每行带 _status/_error 供 celery 摘要计数；pc_summary 汇总 PC 级状态分类。
    错误详情脱敏（不落凭据）且截断到 500 字符。
    """
    format_data = {"add": [], "update": [], "delete": [], "association": []}
    pc_summary = {
        "pc_total": 0,
        "pc_complete": 0,
        "pc_partial": 0,
        "pc_failed": 0,
        "software_added": 0,
        "software_updated": 0,
        "software_deleted": 0,
    }
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
        pc_failed = bool(result.get("pc_failed"))
        software_partial = bool(result.get("software_failed") or result.get("delete_failed"))
        target_partial = software_partial or snapshot.status != "complete"
        pc_row = {
            "inst_name": inst_name,
            "model_id": "pc",
            "_status": "failed" if pc_failed else "success",
            "_error": result.get("error_code", "") if pc_failed else "",
        }
        if result.get("error_detail"):
            pc_row["_error_detail"] = result["error_detail"][:_MAX_ERROR_DETAIL]
        if result.get("pc_status") == "added":
            format_data["add"].append(pc_row)
        else:
            format_data["update"].append(pc_row)
        result_row = {
            "inst_name": inst_name,
            "_status": "failed" if pc_failed or software_partial else "success",
            "_error": result.get("error_code", ""),
        }
        if result.get("error_detail"):
            result_row["_error_detail"] = result["error_detail"][:_MAX_ERROR_DETAIL]
        rows.append(result_row)

        for sw_name, sw_status in result.get("outcomes") or []:
            format_data["association"].append(
                {
                    "inst_name": sw_name,
                    "model_id": "pc_software",
                    "_status": sw_status,
                    "_error": "CMDB_WRITE_PARTIAL" if sw_status == "failed" else "",
                }
            )
        for name in result.get("deleted_names") or []:
            format_data["delete"].append({"inst_name": name, "model_id": "pc_software", "_status": "success", "_error": ""})
        for name in result.get("failed_names") or []:
            format_data["delete"].append({"inst_name": name, "model_id": "pc_software", "_status": "failed", "_error": "CMDB_WRITE_PARTIAL"})

        pc_summary["pc_total"] += 1
        if pc_failed:
            pc_summary["pc_failed"] += 1
        elif target_partial:
            pc_summary["pc_partial"] += 1
        else:
            pc_summary["pc_complete"] += 1
        pc_summary["software_added"] += result.get("software_added", 0)
        pc_summary["software_updated"] += result.get("software_updated", 0)
        pc_summary["software_deleted"] += result.get("software_deleted", 0)

    format_data["all"] = pc_summary["pc_total"]
    format_data["pc_summary"] = pc_summary
    logger.info("[PC] apply_pc_snapshots: task=%s pc_summary=%s", getattr(task, "id", None), pc_summary)
    return {"format_data": format_data, "snapshots": len(snapshots or []), "results": rows}


def _metric_collect_failed(metric):
    return str(metric.get("collect_status", "")).lower() == "failed" or bool(metric.get("cmdb_collect_error"))


def _is_pc_root_metric(metric):
    return metric.get("__name__") in _PC_METRIC_NAMES or metric.get("bk_obj_id") == "pc"


def pc_rows_from_vm_result(result_rows):
    """从 VM 查询行取出 PC / 软件指标。序列名 pc_info_gauge 与逻辑名 pc_info 都收。"""
    rows = []
    for item in result_rows or []:
        if not isinstance(item, dict):
            continue
        metric = item.get("metric")
        if not isinstance(metric, dict):
            continue
        name = metric.get("__name__")
        obj_id = metric.get("bk_obj_id")
        if _metric_collect_failed(metric):
            continue
        recognized = name in _PC_METRIC_NAMES or name in _PC_SOFTWARE_METRIC_NAMES or obj_id in {"pc", "pc_software"}
        if not recognized:
            continue
        row = dict(metric)
        if row.get("_metric_time") in (None, ""):
            value = item.get("value")
            if isinstance(value, (list, tuple)) and value:
                row["_metric_time"] = value[0]
        rows.append(row)
    return rows


def _failed_pc_target_keys(result_rows):
    """失败的 PC 根行只用于任务计数。软件失败行不单独算一台 PC。"""
    keys = []
    seen = set()
    for item in result_rows or []:
        if not isinstance(item, dict):
            continue
        metric = item.get("metric")
        if not isinstance(metric, dict) or not _metric_collect_failed(metric) or not _is_pc_root_metric(metric):
            continue
        key = str(metric.get("collection_target") or metric.get("inst_name") or "")
        if not key:
            key = f"__failed_{len(keys)}"
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def _snapshot_identity_keys(snapshots):
    reported = set()
    for snapshot in snapshots or []:
        pc = getattr(snapshot, "pc", None) or {}
        for value in (pc.get("collection_target"), pc.get("inst_name")):
            text = str(value or "")
            if text:
                reported.add(text)
    return reported


def _record_unreported_pc_failures(format_data, failed_keys, snapshots):
    reported = _snapshot_identity_keys(snapshots)
    extra = [key for key in failed_keys if key not in reported]
    if not extra:
        return format_data
    summary = format_data["pc_summary"]
    summary["pc_failed"] += len(extra)
    summary["pc_total"] += len(extra)
    format_data["all"] = summary["pc_total"]
    for key in extra:
        format_data["update"].append(
            {
                "inst_name": key,
                "model_id": "pc",
                "_status": "failed",
                "_error": "COLLECT_FAILED",
            }
        )
    return format_data


def reconcile_pc_vm_result(task, result_rows, reader_factory=None):
    """用 VM 里的 pc_info_gauge / pc_software_info_gauge 对账。没有完成标记时按 partial 写入。"""
    failed_keys = _failed_pc_target_keys(result_rows)
    rows = pc_rows_from_vm_result(result_rows)
    metadata = {}
    pc_roots = [row for row in rows if _is_pc_root_metric(row)]
    if pc_roots and reader_factory is not None:
        try:
            metadata = reader_factory(task).get_many(build_round_metadata_lookups(pc_roots), model_id="pc")
        except RoundMetadataProtocolError as exc:
            logger.info(
                "[PC] event=pc_partial_without_round_metadata task_id=%s error_type=%s",
                getattr(task, "id", None),
                type(exc).__name__,
            )
            metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    snapshots = parse_pc_vm_rows(rows, metadata)
    format_data = apply_pc_snapshots(task, snapshots)["format_data"]
    return _record_unreported_pc_failures(format_data, failed_keys, snapshots)


def pc_reconcile_input(plugin):
    """企业插件 run() 把 VM 结果放在 raw_data；只调 format_metrics 时行在分桶里。"""
    raw = getattr(plugin, "raw_data", None) or []
    if raw and isinstance(raw[0], dict) and isinstance(raw[0].get("metric"), dict):
        return raw
    rows = []
    seen = set()
    for bucket in getattr(plugin, "collection_metrics_dict", {}).values():
        if id(bucket) in seen:
            continue
        seen.add(id(bucket))
        for metric in bucket or []:
            if isinstance(metric, dict):
                rows.append({"metric": metric, "value": [metric.get("_metric_time"), "1"]})
    return rows


def publish_pc_collected_metrics(plugin):
    """按 VM 序列名把已上报 PC 写入 CMDB，并避免空 metrics 被通用对账当成全量删除。"""
    format_data = reconcile_pc_vm_result(
        plugin.get_collect_inst(),
        pc_reconcile_input(plugin),
        reader_factory=getattr(plugin, "round_metadata_reader_factory", None),
    )
    task_key = getattr(plugin, "TASK_FORMAT_DATA_KEY", "__task_format_data__")
    plugin.result[task_key] = format_data
    plugin._MODEL_ID = None
    return format_data


def install_pc_vm_metric_reconcile():
    """企业 PC 插件的 run() 不走 CollectBase.run，对账入口是它自己的 format_metrics。"""
    try:
        from apps.cmdb_enterprise.collect.pc import PCCollectionPlugin
    except ImportError:
        return
    if getattr(PCCollectionPlugin, "_pc_vm_metric_reconcile", False):
        return

    def format_metrics(self):
        return publish_pc_collected_metrics(self)

    PCCollectionPlugin.format_metrics = format_metrics
    PCCollectionPlugin._pc_vm_metric_reconcile = True


def cleanup_expired_pc_software(task, threshold_dt, threshold_iso):
    """after_expiration 分流：只删除该任务拥有 PC 下 collect_time 早于阈值的软件。

    严禁删除 PC 实体本身；删除仍写 DELETE_INST 审计。
    """
    from apps.cmdb.services.data_cleanup_service import DataCleanupService

    deleted = []
    failed = 0
    with GraphClient() as ag:
        pcs, _ = ag.query_entity(
            INSTANCE,
            [
                {"field": "collect_task", "type": "int=", "value": task.id},
                {"field": "model_id", "type": "str=", "value": "pc"},
            ],
        )
        for pc in pcs:
            edges = ag.query_edge(
                INSTANCE_ASSOCIATION,
                [
                    {"field": "dst_inst_id", "type": "int=", "value": pc["_id"]},
                    {"field": "asst_id", "type": "str=", "value": "install_on"},
                    {"field": "model_asst_id", "type": "str=", "value": "pc_software_install_on_pc"},
                ],
            )
            for edge in edges:
                src_id = edge.get("src_inst_id")
                items, _ = ag.query_entity(
                    INSTANCE,
                    [
                        {"field": "model_id", "type": "str=", "value": "pc_software"},
                        {"field": "_id", "type": "id=", "value": src_id},
                    ],
                )
                if not items:
                    continue
                entity = items[0]
                collect_time = DataCleanupService.parse_collect_time(entity.get("collect_time"))
                if not collect_time or collect_time >= threshold_dt:
                    continue
                try:
                    ag.detach_delete_entity(INSTANCE, src_id)
                    deleted.append(entity)
                except Exception as exc:  # noqa: BLE001 - 单条失败保留，下轮重试
                    logger.warning(
                        "[PC] expired software delete failed: task=%s sw=%s err=%s",
                        task.id,
                        entity.get("inst_name"),
                        type(exc).__name__,
                    )
                    failed += 1
    if deleted:
        PCSnapshotReconciler(task)._write_delete_audit(deleted, f"expire:{threshold_iso}")
    logger.info("[PC] 过期软件清理完成 task=%s deleted=%s failed=%s", task.id, len(deleted), failed)
    result = {
        "task_id": task.id,
        "model_id": "pc_software",
        "deleted_count": len(deleted),
        "deleted_ids": [entity["_id"] for entity in deleted],
        "threshold": threshold_iso,
    }
    if failed:
        result["failed_count"] = failed
    return result
