from apps.cmdb.constants.constants import OPERATOR_INSTANCE
from apps.cmdb.models.change_record import (
    CREATE_INST_ASST,
    CUSTOM_REPORTING_CHANGE,
    ORDINARY_ATTRIBUTE_CHANGE,
    RELATION_CHANGE,
    ChangeRecord,
)


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


def batch_create_change_record(label, _type, change_records, operator="", scenario=ORDINARY_ATTRIBUTE_CHANGE):
    """创建实例变更记录"""
    batch_change_data = [
        ChangeRecord(label=label, type=_type, operator=operator, scenario=scenario, **change_record)
        for change_record in change_records
    ]
    ChangeRecord.objects.bulk_create(batch_change_data)


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
