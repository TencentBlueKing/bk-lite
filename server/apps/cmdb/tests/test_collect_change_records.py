from types import SimpleNamespace

from apps.cmdb.collection.change_records import write_collect_instance_change_records
from apps.cmdb.constants.constants import INSTANCE, OPERATOR_INSTANCE
from apps.cmdb.models.change_record import COLLECT_AUTOMATION_CHANGE, DELETE_INST, UPDATE_INST
from apps.cmdb.utils.change_record import format_instance_audit_message


def test_collect_update_success_writes_no_change_instance_log(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.cmdb.collection.change_records.batch_create_change_record",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    old_instance = {
        "_id": 1,
        "model_id": "host",
        "inst_name": "h1",
        "version": "1.0",
        "collect_time": "old",
    }
    new_instance = {
        "_id": 1,
        "model_id": "host",
        "inst_name": "h1",
        "version": "1.0",
        "collect_time": "new",
        "auto_collect": True,
        "collect_task": "task-1",
    }

    write_collect_instance_change_records(
        SimpleNamespace(model_id="host", old_data=[old_instance], task_name="接口采集"),
        {"add": {"success": []}, "update": {"success": [{"inst_info": new_instance}]}, "delete": {"success": []}},
    )

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:2] == (INSTANCE, UPDATE_INST)
    assert kwargs["scenario"] == COLLECT_AUTOMATION_CHANGE
    record = args[2][0]
    assert record["inst_id"] == 1
    assert record["model_id"] == "host"
    assert record["before_data"] == old_instance
    assert record["after_data"] == new_instance
    assert record["model_object"] == OPERATOR_INSTANCE
    assert record["message"] == "自动采集核实实例，无字段变化. 任务:接口采集 模型:host 实例:h1"
    assert record["content_hash"]


def test_collect_update_ignores_internal_operation_id_when_deciding_verify(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.cmdb.collection.change_records.batch_create_change_record",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    old_instance = {
        "_id": 1,
        "model_id": "host",
        "inst_name": "h1",
        "version": "1.0",
        "_cmdb_operation_id": "old-op",
    }
    new_instance = {
        "_id": 1,
        "model_id": "host",
        "inst_name": "h1",
        "version": "1.0",
        "_cmdb_operation_id": "new-op",
    }

    write_collect_instance_change_records(
        SimpleNamespace(model_id="host", old_data=[old_instance], task_name="主机采集"),
        {"add": {"success": []}, "update": {"success": [{"inst_info": new_instance}]}, "delete": {"success": []}},
    )

    record = calls[0][0][2][0]
    assert record["message"].startswith("自动采集核实实例，无字段变化")
    assert record["content_hash"]


def test_collect_delete_success_writes_delete_instance_log(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.cmdb.collection.change_records.batch_create_change_record",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    deleted_instance = {"_id": 9, "model_id": "pc_software", "inst_name": "SW-OLD", "version": "1.0"}

    write_collect_instance_change_records(
        SimpleNamespace(model_id="pc_software", old_data=[deleted_instance], task_name="终端采集"),
        {"add": {"success": []}, "update": {"success": []}, "delete": {"success": [deleted_instance]}},
    )

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:2] == (INSTANCE, DELETE_INST)
    assert kwargs["operator"] == "system"
    assert kwargs["scenario"] == COLLECT_AUTOMATION_CHANGE
    record = args[2][0]
    assert record["inst_id"] == 9
    assert record["model_id"] == "pc_software"
    assert record["before_data"] == deleted_instance
    assert "after_data" not in record or not record["after_data"]
    assert record["model_object"] == OPERATOR_INSTANCE
    assert record["message"] == "自动采集删除实例. 任务:终端采集 模型:pc_software 实例:SW-OLD"


def test_instance_audit_message_inserts_source_and_keeps_plain_sentence():
    assert format_instance_audit_message("创建模型实例", "host", "10.0.0.1") == "创建模型实例. 模型:host 实例:10.0.0.1"
    assert format_instance_audit_message("创建模型实例", "host", "10.0.0.1", source="节点同步") == "创建模型实例. 来源:节点同步 模型:host 实例:10.0.0.1"
    assert format_instance_audit_message("删除模型实例", "主机", "db-1", source="手动") == "删除模型实例. 来源:手动 模型:主机 实例:db-1"
    assert format_instance_audit_message("修改模型实例属性", "主机", "db-1", source="  ") == "修改模型实例属性. 模型:主机 实例:db-1"
