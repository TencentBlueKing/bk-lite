"""自动采集实例级操作日志。"""

from apps.cmdb.constants.constants import INSTANCE, OPERATOR_INSTANCE
from apps.cmdb.models.change_record import COLLECT_AUTOMATION_CHANGE, CREATE_INST, DELETE_INST, UPDATE_INST
from apps.cmdb.utils.change_record import batch_create_change_record, verify_content_hash

SYSTEM_COLLECT_FIELDS = {"_id", "model_id", "collect_time", "collect_task", "auto_collect", "_collect_sources", "manual_fields", "_cmdb_operation_id"}


def write_collect_instance_change_records(management, result: dict):
    task_name = str(getattr(management, "task_name", "") or "").strip()
    add_records = _build_add_records(result.get("add", {}).get("success", []), task_name)
    update_records = _build_update_records(management, result.get("update", {}).get("success", []), task_name)
    delete_records = _build_delete_records(result.get("delete", {}).get("success", []), task_name)

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
    if delete_records:
        batch_create_change_record(
            INSTANCE,
            DELETE_INST,
            delete_records,
            operator="system",
            scenario=COLLECT_AUTOMATION_CHANGE,
        )


def _build_delete_records(success_items: list[dict], task_name: str) -> list[dict]:
    records = []
    for item in success_items:
        instance = _success_instance(item)
        if not instance:
            continue
        records.append(
            {
                "inst_id": instance["_id"],
                "model_id": instance["model_id"],
                "before_data": instance,
                "model_object": OPERATOR_INSTANCE,
                "message": _message("自动采集删除实例", instance, task_name),
            }
        )
    return records


def _build_add_records(success_items: list[dict], task_name: str) -> list[dict]:
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
                "message": _message("自动采集新增实例", instance, task_name),
            }
        )
    return records


def _build_update_records(management, success_items: list[dict], task_name: str) -> list[dict]:
    old_instances = {item.get("_id"): item for item in getattr(management, "old_data", []) or [] if item.get("_id") is not None}
    records = []
    for item in success_items:
        if item.get("suppress_change_record"):
            continue
        instance = _success_instance(item)
        if not instance:
            continue
        before_data = old_instances.get(instance["_id"], {})
        title = "自动采集更新实例"
        content_hash = ""
        if not _changed_business_fields(before_data, instance):
            title = "自动采集核实实例，无字段变化"
            content_hash = verify_content_hash(instance["_id"], instance["model_id"], UPDATE_INST)
        record = {
            "inst_id": instance["_id"],
            "model_id": instance["model_id"],
            "before_data": before_data,
            "after_data": instance,
            "model_object": OPERATOR_INSTANCE,
            "message": _message(title, instance, task_name),
        }
        if content_hash:
            record["content_hash"] = content_hash
        records.append(record)
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


def _message(title: str, instance: dict, task_name: str = "") -> str:
    instance_name = instance.get("inst_name") or instance.get("ip_addr") or instance.get("_id")
    task_part = f"任务:{task_name} " if task_name else ""
    return f"{title}. {task_part}模型:{instance.get('model_id')} 实例:{instance_name}"
