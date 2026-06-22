from apps.cmdb.constants.constants import OPERATOR_INSTANCE
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
from apps.core.logger import cmdb_logger as logger
from apps.rpc.system_mgmt import SystemMgmt

# 需要镜像进平台操作日志的"管理类"变更场景
_MIRROR_SCENARIOS = {MODEL_MANAGEMENT_CHANGE, COLLECT_AUTOMATION_CHANGE, CUSTOM_REPORTING_CHANGE, RELATION_CHANGE}
_TYPE_ACTION_MAP = {
    CREATE_INST: "create",
    UPDATE_INST: "update",
    DELETE_INST: "delete",
    CREATE_INST_ASST: "create",
    DELETE_INST_ASST: "delete",
    EXECUTE: "execute",
}


def _mirror_change_record(*, inst_id, model_id, _type, operator, scenario,
                          message="", model_object="", before_data=None, after_data=None):
    """将管理类变更记录经 NATS RPC 镜像进平台操作日志。失败绝不影响源写入。"""
    if scenario not in _MIRROR_SCENARIOS:
        return
    try:
        SystemMgmt().save_operation_log(
            username=operator or "system",
            source_ip="127.0.0.1",
            app="cmdb",
            action_type=_TYPE_ACTION_MAP.get(_type, "execute"),
            summary=message or f"{_type}: {model_object or model_id}",
            target_type=model_object or model_id,
            target_id=str(inst_id),
            detail={"before_data": before_data or {}, "after_data": after_data or {},
                    "scenario": scenario, "model_object": model_object, "source": "change_record"},
        )
    except Exception as e:  # noqa: 镜像失败绝不影响源写入
        logger.warning(f"mirror change_record to operation_log failed: {e}")


def create_change_record(inst_id, model_id, label, _type, before_data=None, after_data=None, operator="", message="",
                         model_object="", scenario=ORDINARY_ATTRIBUTE_CHANGE):
    """创建实例变更记录"""
    change_data = {"operator": operator, "scenario": scenario}
    if before_data:
        change_data["before_data"] = before_data
    if after_data:
        change_data["after_data"] = after_data
    if message:
        change_data["message"] = message
    if model_object:
        change_data["model_object"] = model_object
    ChangeRecord.objects.create(inst_id=inst_id, model_id=model_id, label=label, type=_type, **change_data)
    _mirror_change_record(inst_id=inst_id, model_id=model_id, _type=_type, operator=operator, scenario=scenario,
                          message=message, model_object=model_object, before_data=before_data, after_data=after_data)


def batch_create_change_record(label, _type, change_records, operator="", scenario=ORDINARY_ATTRIBUTE_CHANGE):
    """创建实例变更记录"""
    batch_change_data = [
        ChangeRecord(label=label, type=_type, operator=operator, scenario=scenario, **change_record)
        for change_record in change_records
    ]
    ChangeRecord.objects.bulk_create(batch_change_data)
    for rec in change_records:
        _mirror_change_record(inst_id=rec.get("inst_id"), model_id=rec.get("model_id"), _type=_type,
                              operator=operator, scenario=scenario, message=rec.get("message", ""),
                              model_object=rec.get("model_object", ""),
                              before_data=rec.get("before_data"), after_data=rec.get("after_data"))


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
    )


def create_change_record_by_asso(label, _type, data, operator="", message="", scenario=RELATION_CHANGE):
    """创建关联关系变更记录"""

    change_data = {"operator": operator, "scenario": scenario}

    if _type == CREATE_INST_ASST:
        change_data["after_data"] = data
    else:
        change_data["before_data"] = data

    batch_change_data = [
        ChangeRecord(inst_id=inst_info["_id"], model_id=inst_info["model_id"], model_object=OPERATOR_INSTANCE,
                     message=message, label=label, type=_type,
                     **change_data)
        for inst_info in [data["src"], data["dst"]]
        if inst_info.get("model_id")
    ]

    ChangeRecord.objects.bulk_create(batch_change_data)
    for inst_info in [data["src"], data["dst"]]:
        if not inst_info.get("model_id"):
            continue
        _mirror_change_record(inst_id=inst_info["_id"], model_id=inst_info["model_id"], _type=_type,
                              operator=operator, scenario=scenario, message=message,
                              model_object=OPERATOR_INSTANCE,
                              before_data=change_data.get("before_data"),
                              after_data=change_data.get("after_data"))
