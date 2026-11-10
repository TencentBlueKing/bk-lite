import hashlib

from django.db.models import Max
from django.utils.timezone import now

from apps.cmdb.constants.constants import INSTANCE, OPERATOR_INSTANCE
from apps.cmdb.models.change_record import (
    COLLECT_AUTOMATION_CHANGE,
    CREATE_INST,
    CREATE_INST_ASST,
    CUSTOM_REPORTING_CHANGE,
    DELETE_INST,
    DELETE_INST_ASST,
    EXECUTE,
    MODEL_MANAGEMENT_CHANGE,
    ORDINARY_ATTRIBUTE_CHANGE,
    RELATION_CHANGE,
    UPDATE_INST,
    ChangeRecord,
)

# 需要镜像进平台操作日志的"管理类"变更场景
_MIRROR_SCENARIOS = {MODEL_MANAGEMENT_CHANGE, COLLECT_AUTOMATION_CHANGE, CUSTOM_REPORTING_CHANGE, RELATION_CHANGE}
VERIFY_MESSAGE_PREFIX = "自动采集核实实例，无字段变化"
_TYPE_ACTION_MAP = {
    CREATE_INST: "create",
    UPDATE_INST: "update",
    DELETE_INST: "delete",
    CREATE_INST_ASST: "create",
    DELETE_INST_ASST: "delete",
    EXECUTE: "execute",
}


def verify_content_hash(inst_id, model_id, change_type: str) -> str:
    """同一实例反复核实、字段没变时使用的稳定标识。不包含时间、采集任务号。"""
    raw = f"{inst_id}|{model_id}|{change_type}|verify"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_verify_only_message(message: str) -> bool:
    return str(message or "").startswith(VERIFY_MESSAGE_PREFIX)


def format_instance_audit_message(action: str, model: str, inst_name: str, *, source: str = "") -> str:
    """实例变更概述。有来源时插在动作和模型之间，没有来源时保持原句。"""
    source_text = str(source or "").strip()
    source_part = f"来源:{source_text} " if source_text else ""
    return f"{action}. {source_part}模型:{model} 实例:{inst_name}"


def _resolve_inst_uuid(inst_uuid=None, before_data=None, after_data=None):
    return inst_uuid or (after_data or {}).get("inst_uuid") or (before_data or {}).get("inst_uuid") or None


def _table_candidate_fields(data: dict | None) -> set[str]:
    fields = set()
    for key, value in (data or {}).items():
        if isinstance(value, list) and any(isinstance(item, dict) for item in value):
            fields.add(key)
        elif isinstance(value, str) and value.lstrip().startswith("[{"):
            fields.add(key)
    return fields


def _build_mirror_payload(*, inst_id, model_id, _type, operator, scenario, message="", model_object="", before_data=None, after_data=None):
    return {
        "username": operator or "system",
        "source_ip": "127.0.0.1",
        "app": "cmdb",
        "action_type": _TYPE_ACTION_MAP.get(_type, "execute"),
        "summary": message or f"{_type}: {model_object or model_id}",
        "target_type": model_object or model_id,
        "target_id": str(inst_id),
        "detail": {
            "before_data": before_data or {},
            "after_data": after_data or {},
            "scenario": scenario,
            "model_object": model_object,
            "source": "change_record",
        },
    }


def _mirror_change_record(*, inst_id, model_id, _type, operator, scenario, message="", model_object="", before_data=None, after_data=None):
    """管理类变更写入镜像 outbox，由周期任务批量推送。无变化核实不进入日志平台。"""
    if scenario not in _MIRROR_SCENARIOS or is_verify_only_message(message):
        return
    from apps.cmdb.services.change_record_mirror import ChangeRecordMirrorService

    ChangeRecordMirrorService.enqueue_payloads(
        [
            _build_mirror_payload(
                inst_id=inst_id,
                model_id=model_id,
                _type=_type,
                operator=operator,
                scenario=scenario,
                message=message,
                model_object=model_object,
                before_data=before_data,
                after_data=after_data,
            )
        ]
    )


def create_change_record(
    inst_id,
    model_id,
    label,
    _type,
    before_data=None,
    after_data=None,
    operator="",
    message="",
    model_object="",
    scenario=ORDINARY_ATTRIBUTE_CHANGE,
    operation_event_id=None,
    inst_uuid=None,
    attribute_snapshot=None,
):
    """创建实例变更记录"""
    if label == INSTANCE and not attribute_snapshot and model_id:
        attr_ids = _table_candidate_fields(before_data) | _table_candidate_fields(after_data)
        if attr_ids:
            from apps.cmdb.services.change_record_snapshot import load_attribute_snapshot

            attribute_snapshot = load_attribute_snapshot(model_id, attr_ids)
    resolved_uuid = _resolve_inst_uuid(inst_uuid, before_data, after_data)
    from apps.cmdb.collection.field_reconcile import hide_collect_sources

    before_data = hide_collect_sources(before_data)
    after_data = hide_collect_sources(after_data)
    change_data = {"operator": operator, "scenario": scenario, "inst_uuid": resolved_uuid}
    if before_data:
        change_data["before_data"] = before_data
    if after_data:
        change_data["after_data"] = after_data
    if message:
        change_data["message"] = message
    if model_object:
        change_data["model_object"] = model_object
    if attribute_snapshot:
        change_data["attribute_snapshot"] = attribute_snapshot
    if operation_event_id:
        _record, created = ChangeRecord.objects.get_or_create(
            operation_event_id=operation_event_id,
            defaults={"inst_id": inst_id, "model_id": model_id, "label": label, "type": _type, **change_data},
        )
    else:
        _record = ChangeRecord.objects.create(
            inst_id=inst_id,
            model_id=model_id,
            label=label,
            type=_type,
            **change_data,
        )
        created = True
    if created:
        _mirror_change_record(
            inst_id=inst_id,
            model_id=model_id,
            _type=_type,
            operator=operator,
            scenario=scenario,
            message=message,
            model_object=model_object,
            before_data=before_data,
            after_data=after_data,
        )
    return _record


def _is_same_verify(latest: ChangeRecord, content_hash: str) -> bool:
    if latest.content_hash and latest.content_hash == content_hash:
        return True
    return not latest.content_hash and is_verify_only_message(latest.message)


def _latest_by_inst(inst_ids: list[int]) -> dict[int, ChangeRecord]:
    latest: dict[int, ChangeRecord] = {}
    for offset in range(0, len(inst_ids), 500):
        chunk = inst_ids[offset : offset + 500]
        id_rows = ChangeRecord.objects.filter(inst_id__in=chunk).values("inst_id").annotate(latest_id=Max("id"))
        rows = ChangeRecord.objects.filter(id__in=[row["latest_id"] for row in id_rows])
        latest.update({row.inst_id: row for row in rows})
    return latest


def _collapse_verify_records(records: list[dict], *, operator: str, scenario: str) -> tuple[list[dict], int]:
    """同一实例的无变化核实只保留最后一条。和上一条核实用同一个哈希时，只刷新时间。"""
    pending: dict[int, dict] = {}
    order: list[int] = []
    inserts: list[dict] = []
    for record in records:
        content_hash = record.get("content_hash") or ""
        inst_id = record.get("inst_id")
        if not content_hash or inst_id is None:
            inserts.append(record)
            continue
        if inst_id not in pending:
            order.append(inst_id)
        pending[inst_id] = record
    if not pending:
        return inserts, 0
    latest = _latest_by_inst(order)
    refreshed = 0
    current_time = now()
    for inst_id in order:
        record = pending[inst_id]
        previous = latest.get(inst_id)
        if previous is not None and _is_same_verify(previous, record["content_hash"]):
            ChangeRecord.objects.filter(pk=previous.pk).update(
                created_at=current_time,
                before_data=record.get("before_data") or {},
                after_data=record.get("after_data") or {},
                message=record.get("message", ""),
                content_hash=record["content_hash"],
                operator=operator,
                scenario=scenario,
                model_object=record.get("model_object", ""),
            )
            refreshed += 1
            continue
        inserts.append(record)
    return inserts, refreshed


def batch_create_change_record(label, _type, change_records, operator="", scenario=ORDINARY_ATTRIBUTE_CHANGE):
    """创建实例变更记录"""
    normalized_records = []
    for change_record in change_records:
        record = dict(change_record)
        from apps.cmdb.collection.field_reconcile import hide_collect_sources

        if record.get("before_data"):
            record["before_data"] = hide_collect_sources(record["before_data"])
        if record.get("after_data"):
            record["after_data"] = hide_collect_sources(record["after_data"])
        record.setdefault(
            "inst_uuid",
            _resolve_inst_uuid(
                record.get("inst_uuid"),
                record.get("before_data"),
                record.get("after_data"),
            ),
        )
        normalized_records.append(record)
    if label == INSTANCE:
        from apps.cmdb.services.change_record_snapshot import load_attribute_snapshot

        fields_by_model: dict[str, set[str]] = {}
        for record in normalized_records:
            if record.get("attribute_snapshot") or not record.get("model_id"):
                continue
            attr_ids = _table_candidate_fields(record.get("before_data")) | _table_candidate_fields(record.get("after_data"))
            if attr_ids:
                fields_by_model.setdefault(record["model_id"], set()).update(attr_ids)
        snapshots = {model_id: load_attribute_snapshot(model_id, attr_ids) for model_id, attr_ids in fields_by_model.items()}
        for record in normalized_records:
            if not record.get("attribute_snapshot") and record.get("model_id") in snapshots:
                record["attribute_snapshot"] = snapshots[record["model_id"]]
    to_insert, _refreshed = _collapse_verify_records(normalized_records, operator=operator, scenario=scenario)
    if to_insert:
        ChangeRecord.objects.bulk_create(
            [ChangeRecord(label=label, type=_type, operator=operator, scenario=scenario, **record) for record in to_insert]
        )
    if scenario in _MIRROR_SCENARIOS:
        from apps.cmdb.services.change_record_mirror import ChangeRecordMirrorService

        payloads = [
            _build_mirror_payload(
                inst_id=rec.get("inst_id"),
                model_id=rec.get("model_id"),
                _type=_type,
                operator=operator,
                scenario=scenario,
                message=rec.get("message", ""),
                model_object=rec.get("model_object", ""),
                before_data=rec.get("before_data"),
                after_data=rec.get("after_data"),
            )
            for rec in to_insert
            if not rec.get("content_hash") and not is_verify_only_message(rec.get("message", ""))
        ]
        if payloads:
            ChangeRecordMirrorService.enqueue_payloads(payloads)
    return _refreshed


def create_custom_reporting_change_record(
    inst_id,
    model_id,
    label,
    _type,
    before_data=None,
    after_data=None,
    operator="",
    message="",
    model_object="",
    inst_uuid=None,
):
    return create_change_record(
        inst_id=inst_id,
        model_id=model_id,
        label=label,
        _type=_type,
        before_data=before_data,
        after_data=after_data,
        operator=operator,
        message=message,
        model_object=model_object,
        scenario=CUSTOM_REPORTING_CHANGE,
        inst_uuid=inst_uuid,
    )


def create_change_record_by_asso(label, _type, data, operator="", message="", scenario=RELATION_CHANGE):
    """创建关联关系变更记录"""

    change_data = {"operator": operator, "scenario": scenario}

    if _type == CREATE_INST_ASST:
        change_data["after_data"] = data
    else:
        change_data["before_data"] = data

    batch_change_data = [
        ChangeRecord(
            inst_id=inst_info.get("_id"),
            inst_uuid=inst_info.get("inst_uuid"),
            model_id=inst_info["model_id"],
            model_object=OPERATOR_INSTANCE,
            message=message,
            label=label,
            type=_type,
            **change_data,
        )
        for inst_info in [data["src"], data["dst"]]
        if inst_info.get("model_id")
    ]

    ChangeRecord.objects.bulk_create(batch_change_data)
    mirror_records = [
        {
            "inst_id": inst_info.get("_id"),
            "model_id": inst_info["model_id"],
            "message": message,
            "model_object": OPERATOR_INSTANCE,
            "before_data": change_data.get("before_data"),
            "after_data": change_data.get("after_data"),
        }
        for inst_info in [data["src"], data["dst"]]
        if inst_info.get("model_id")
    ]
    if mirror_records and not is_verify_only_message(message):
        from apps.cmdb.services.change_record_mirror import ChangeRecordMirrorService

        ChangeRecordMirrorService.enqueue_payloads(
            [
                _build_mirror_payload(
                    inst_id=rec["inst_id"],
                    model_id=rec["model_id"],
                    _type=_type,
                    operator=operator,
                    scenario=scenario,
                    message=rec["message"],
                    model_object=rec["model_object"],
                    before_data=rec["before_data"],
                    after_data=rec["after_data"],
                )
                for rec in mirror_records
            ]
        )
