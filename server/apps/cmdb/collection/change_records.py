"""自动采集实例级操作日志。"""

from apps.cmdb.constants.constants import INSTANCE, OPERATOR_INSTANCE
from apps.cmdb.models.change_record import COLLECT_AUTOMATION_CHANGE, CREATE_INST, UPDATE_INST
from apps.cmdb.utils.change_record import batch_create_change_record

SYSTEM_COLLECT_FIELDS = {"_id", "model_id", "collect_time", "collect_task", "auto_collect"}


def write_collect_instance_change_records(management, result: dict):
    add_records = _build_add_records(result.get("add", {}).get("success", []))
    update_records = _build_update_records(management, result.get("update", {}).get("success", []))

    if add_records:
        batch_create_change_record(
            INSTANCE,
            CREATE_INST,
            add_records,
            operator="system",
            scenario=COLLECT_AUTOMATION_CHANGE,
        )
    if update_records:
        batch_create_change_record(
            INSTANCE,
            UPDATE_INST,
            update_records,
            operator="system",
            scenario=COLLECT_AUTOMATION_CHANGE,
        )


def _build_add_records(success_items: list[dict]) -> list[dict]:
    records = []
    for item in success_items:
        instance = _success_instance(item)
        if not instance:
            continue
        records.append(
            {
                "inst_id": instance["_id"],
                "model_id": instance["model_id"],
                "after_data": instance,
                "model_object": OPERATOR_INSTANCE,
                "message": _message("自动采集新增实例", instance),
            }
        )
    return records


def _build_update_records(management, success_items: list[dict]) -> list[dict]:
    old_instances = {item.get("_id"): item for item in getattr(management, "old_data", []) or [] if item.get("_id") is not None}
    records = []
    for item in success_items:
        instance = _success_instance(item)
        if not instance:
            continue
        before_data = old_instances.get(instance["_id"], {})
        title = "自动采集更新实例"
        if not _changed_business_fields(before_data, instance):
            title = "自动采集核实实例，无字段变化"
        records.append(
            {
                "inst_id": instance["_id"],
                "model_id": instance["model_id"],
                "before_data": before_data,
                "after_data": instance,
                "model_object": OPERATOR_INSTANCE,
                "message": _message(title, instance),
            }
        )
    return records


def _success_instance(item: dict) -> dict:
    if not isinstance(item, dict):
        return {}
    instance = item.get("inst_info", item)
    if not isinstance(instance, dict) or instance.get("_id") is None or not instance.get("model_id"):
        return {}
    return instance


def _changed_business_fields(before_data: dict, after_data: dict) -> list[str]:
    fields = (set(before_data) | set(after_data)) - SYSTEM_COLLECT_FIELDS
    return [field for field in fields if before_data.get(field) != after_data.get(field)]


def _message(title: str, instance: dict) -> str:
    instance_name = instance.get("inst_name") or instance.get("ip_addr") or instance.get("_id")
    return f"{title}. 模型:{instance.get('model_id')} 实例:{instance_name}"
