from types import SimpleNamespace

from apps.cmdb.collection.change_records import write_collect_instance_change_records
from apps.cmdb.constants.constants import INSTANCE, OPERATOR_INSTANCE
from apps.cmdb.models.change_record import COLLECT_AUTOMATION_CHANGE, UPDATE_INST


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
        SimpleNamespace(model_id="host", old_data=[old_instance]),
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
    assert "无字段变化" in record["message"]
