from apps.cmdb.constants import OPERATOR_INSTANCE
from apps.cmdb.models.change_record import CREATE_INST_ASST, ChangeRecord


def create_change_record(inst_id, model_id, label, _type, before_data=None, after_data=None, operator="", message="",
                         model_object=""):
    """创建实例变更记录"""
    change_data = {"operator": operator}
    if before_data:
        change_data["before_data"] = before_data
    if after_data:
        change_data["after_data"] = after_data
    if message:
        change_data["message"] = message
    if model_object:
        change_data["model_object"] = model_object
    ChangeRecord.objects.create(inst_id=inst_id, model_id=model_id, label=label, type=_type, **change_data)


def batch_create_change_record(label, _type, change_records, operator=""):
    """创建实例变更记录"""
    batch_change_data = [
        ChangeRecord(label=label, type=_type, operator=operator, **change_record) for change_record in change_records
    ]
    ChangeRecord.objects.bulk_create(batch_change_data)


def create_change_record_by_asso(label, _type, data, operator="", message=""):
    """创建关联关系变更记录"""

    change_data = {"operator": operator}

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
