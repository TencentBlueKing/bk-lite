import pytest

from apps.cmdb.collect.extensions import CollectEnterpriseExtension
from apps.cmdb.collection.common import Management
from apps.cmdb.extensions import registry


@pytest.fixture(autouse=True)
def _clear_collect_extension():
    saved = registry._registry.get("collect")
    registry._registry.pop("collect", None)
    yield
    if saved is not None:
        registry._registry["collect"] = saved
    else:
        registry._registry.pop("collect", None)


def test_controller_notifies_collect_enterprise_extension(monkeypatch):
    calls = []

    class RecordingExtension(CollectEnterpriseExtension):
        def on_collect_instances_applied(self, *, management, result):
            calls.append((management, result))

    registry.register("collect", RecordingExtension())
    monkeypatch.setattr("apps.cmdb.collection.common.ModelManage.search_model_attr", lambda model_id: [])
    monkeypatch.setattr("apps.cmdb.collection.common.write_collect_instance_change_records", lambda *args, **kwargs: None)

    management = Management(
        organization=["org-a"],
        inst_name="collect-task",
        model_id="host",
        old_data=[{"_id": "old-1", "inst_name": "same"}],
        new_data=[{"inst_name": "same"}, {"inst_name": "new"}],
        unique_keys=["inst_name"],
        collect_time="2026-06-11T00:00:00+00:00",
        task_id="task-1",
    )
    monkeypatch.setattr(management, "delete_inst", lambda inst_list: {"success": inst_list, "failed": []})
    monkeypatch.setattr(management, "add_inst", lambda inst_list: {"success": inst_list, "failed": []})
    monkeypatch.setattr(management, "update_inst", lambda inst_list: {"success": inst_list, "failed": []})

    result = management.controller()

    assert calls == [(management, result)]


def test_update_notifies_collect_enterprise_extension(monkeypatch):
    calls = []

    class RecordingExtension(CollectEnterpriseExtension):
        def on_collect_instances_applied(self, *, management, result):
            calls.append((management, result))

    registry.register("collect", RecordingExtension())
    monkeypatch.setattr("apps.cmdb.collection.common.ModelManage.search_model_attr", lambda model_id: [])
    monkeypatch.setattr("apps.cmdb.collection.common.write_collect_instance_change_records", lambda *args, **kwargs: None)

    management = Management(
        organization=["org-a"],
        inst_name="collect-task",
        model_id="host",
        old_data=[{"_id": "old-1", "inst_name": "same"}],
        new_data=[{"inst_name": "same"}],
        unique_keys=["inst_name"],
        collect_time="2026-06-11T00:00:00+00:00",
        task_id="task-1",
    )
    monkeypatch.setattr(management, "update_inst", lambda inst_list: {"success": inst_list, "failed": []})

    result = management.update()

    assert calls == [(management, result)]
