"""实例操作日志概述落库。

覆盖配置采集任务名、属性变更来源，以及页面/接入/导入把来源写进 ChangeRecord.message。
"""

from types import SimpleNamespace

import pytest

from apps.cmdb.collection.change_records import write_collect_instance_change_records
from apps.cmdb.constants.constants import INSTANCE, OPERATOR_INSTANCE
from apps.cmdb.models.change_record import COLLECT_AUTOMATION_CHANGE, CREATE_INST, DELETE_INST, ORDINARY_ATTRIBUTE_CHANGE, UPDATE_INST, ChangeRecord
from apps.cmdb.models.operation import CmdbOperationOutbox
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.module_ingest import CmdbModuleIngestService
from apps.cmdb.services.operation_service import OperationService
from apps.cmdb.services.pc_discovery import PCSnapshotReconciler
from apps.cmdb.services.transfer_import import TransferImport

pytestmark = pytest.mark.django_db

MODULE = "apps.cmdb.services.instance"
HOST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


@pytest.fixture
def quiet_instance_writes(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile",
        lambda ids: None,
    )
    monkeypatch.setattr(
        f"{MODULE}.schedule_instance_auto_relation_reconcile",
        lambda ids: None,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_incoming_rule_full_sync_by_model_ids",
        lambda model_ids: None,
    )
    monkeypatch.setattr(
        f"{MODULE}.InstanceManage._build_unique_rule_check_attr_map",
        lambda model_id, attrs, for_update=False: {"is_only": {}, "is_required": {}, "unique_rules": [], "attrs_by_id": {}},
    )
    monkeypatch.setattr(
        "apps.cmdb.display_field.DisplayFieldHandler.build_display_fields",
        lambda model_id, info, attrs: info,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr",
        lambda model_id, language="en": [
            {"attr_id": "inst_name", "attr_name": "名称", "attr_type": "str", "is_required": False},
        ],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda model_id: {"model_id": model_id, "model_name": "主机", "attrs": "[]", "_id": 1},
    )
    monkeypatch.setattr(f"{MODULE}.InstanceManage.check_instances_permission", lambda *a, **k: None)
    monkeypatch.setattr(
        f"{MODULE}.InstanceManage._best_effort_notify_peers_on_host_create",
        lambda result, **kwargs: result,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.module_push.CmdbToMonitorPushService.best_effort_notify_on_delete",
        lambda *args, **kwargs: None,
    )


def _message(inst_id):
    return ChangeRecord.objects.get(inst_id=inst_id).message


def test_collect_writes_add_update_verify_and_delete_logs():
    old_changed = {"_id": 1, "model_id": "host", "inst_name": "h1", "version": "1"}
    old_verified = {"_id": 2, "model_id": "interface", "inst_name": "eth0", "speed": "1G"}
    write_collect_instance_change_records(
        SimpleNamespace(
            task_name="交换机接口采集",
            old_data=[old_changed, old_verified],
        ),
        {
            "add": {"success": [{"inst_info": {"_id": 3, "model_id": "host", "inst_name": "new-host"}}]},
            "update": {
                "success": [
                    {"inst_info": {"_id": 1, "model_id": "host", "inst_name": "h1", "version": "2"}},
                    {"inst_info": {"_id": 2, "model_id": "interface", "inst_name": "eth0", "speed": "1G", "collect_time": "new"}},
                    {"inst_info": {"_id": 9, "model_id": "host", "inst_name": "skip"}, "suppress_change_record": True},
                ]
            },
            "delete": {"success": [{"_id": 4, "model_id": "pc_software", "inst_name": "old-sw"}]},
        },
    )

    rows = {row.inst_id: row for row in ChangeRecord.objects.all()}
    assert set(rows) == {1, 2, 3, 4}
    assert rows[3].type == CREATE_INST
    assert rows[3].message == "自动采集新增实例. 任务:交换机接口采集 模型:host 实例:new-host"
    assert rows[1].type == UPDATE_INST
    assert rows[1].message == "自动采集更新实例. 任务:交换机接口采集 模型:host 实例:h1"
    assert rows[2].type == UPDATE_INST
    assert rows[2].message == "自动采集核实实例，无字段变化. 任务:交换机接口采集 模型:interface 实例:eth0"
    assert rows[2].content_hash
    assert not rows[1].content_hash
    assert rows[4].type == DELETE_INST
    assert rows[4].message == "自动采集删除实例. 任务:交换机接口采集 模型:pc_software 实例:old-sw"
    for row in rows.values():
        assert row.operator == "system"
        assert row.scenario == COLLECT_AUTOMATION_CHANGE
        assert row.model_object == OPERATOR_INSTANCE
        assert row.label == INSTANCE


def test_repeated_verify_refreshes_time_and_does_not_mirror():
    from apps.cmdb.models.operation import ChangeRecordMirrorOutbox

    verified = {"_id": 2, "model_id": "interface", "inst_name": "eth0", "speed": "1G"}
    payload = {
        "add": {"success": []},
        "update": {"success": [{"inst_info": {**verified, "collect_time": "first"}}]},
        "delete": {"success": []},
    }
    write_collect_instance_change_records(SimpleNamespace(task_name="交换机接口采集", old_data=[verified]), payload)
    first = ChangeRecord.objects.get(inst_id=2)
    ChangeRecord.objects.filter(pk=first.pk).update(created_at=first.created_at.replace(year=2020))
    first.refresh_from_db()

    payload["update"]["success"][0]["inst_info"]["collect_time"] = "second"
    write_collect_instance_change_records(SimpleNamespace(task_name="交换机接口采集", old_data=[verified]), payload)

    assert ChangeRecord.objects.filter(inst_id=2).count() == 1
    refreshed = ChangeRecord.objects.get(inst_id=2)
    assert refreshed.pk == first.pk
    assert refreshed.created_at > first.created_at
    assert refreshed.content_hash == first.content_hash
    assert ChangeRecordMirrorOutbox.objects.count() == 0


def test_vm_repeat_pull_does_not_duplicate_verify_or_platform_log():
    """周期拉取 VM：关联把实例送进更新，但字段没变时不新增日志，也不推到日志平台。"""
    from apps.cmdb.collection.common import Management
    from apps.cmdb.models.operation import ChangeRecordMirrorOutbox
    from apps.cmdb.services.change_record_mirror import ChangeRecordMirrorService
    from apps.system_mgmt.models.operation_log import OperationLog
    from apps.system_mgmt.nats_api import save_operation_logs

    old = {
        "_id": 101,
        "model_id": "vmware_vm",
        "inst_name": "vm-a",
        "cpu": 2,
        "memory": 4,
        "collect_time": "2026-11-06T10:00:00",
        "collect_task": "vm-task",
        "auto_collect": True,
    }
    pulled = {key: value for key, value in old.items() if key != "_id"}
    pulled["collect_time"] = "2026-11-06T10:05:00"
    pulled["assos"] = [{"model_asst_id": "vmware_vm_run_vmware_esxi", "inst_name": "esxi-1"}]
    assert Management.has_business_changes(old, pulled) is True

    stored = {**old, "collect_time": pulled["collect_time"]}
    _apply_vm_update(old, stored)
    verify = ChangeRecord.objects.get(inst_id=101)
    assert verify.message.startswith("自动采集核实实例，无字段变化")
    assert verify.content_hash
    assert ChangeRecordMirrorOutbox.objects.count() == 0

    heartbeat = {**old, "_id": 102, "inst_name": "vm-b", "collect_time": "2026-11-06T10:05:00"}
    assert Management.has_business_changes({**old, "_id": 102, "inst_name": "vm-b"}, heartbeat) is False
    _apply_vm_update({**old, "_id": 102, "inst_name": "vm-b"}, heartbeat, heartbeat=True)
    assert not ChangeRecord.objects.filter(inst_id=102).exists()

    ChangeRecord.objects.filter(pk=verify.pk).update(created_at=verify.created_at.replace(year=2020))
    verify.refresh_from_db()
    again = {**stored, "collect_time": "2026-11-06T10:10:00"}
    _apply_vm_update(stored, again)
    assert ChangeRecord.objects.filter(inst_id=101).count() == 1
    refreshed = ChangeRecord.objects.get(inst_id=101)
    assert refreshed.pk == verify.pk
    assert refreshed.created_at > verify.created_at
    assert refreshed.content_hash == verify.content_hash
    assert ChangeRecordMirrorOutbox.objects.count() == 0

    changed = {**again, "cpu": 4, "collect_time": "2026-11-06T10:15:00"}
    _apply_vm_update(again, changed)
    assert ChangeRecord.objects.filter(inst_id=101).count() == 2
    assert ChangeRecord.objects.filter(inst_id=101, message__startswith="自动采集更新实例").count() == 1
    [outbox] = list(ChangeRecordMirrorOutbox.objects.all())
    payloads = list(outbox.payloads)
    assert len(payloads) == 1
    assert "无字段变化" not in payloads[0]["summary"]

    assert ChangeRecordMirrorService.consume(outbox.event_id, owner_token="worker-vm") is True
    replay = save_operation_logs(logs=payloads)
    assert replay["result"] is True
    assert replay["duplicates"] == 1
    logs = OperationLog.objects.filter(app="cmdb", target_id="101")
    assert logs.count() == 1
    assert logs.get().summary.startswith("自动采集更新实例")

    unchanged_after_edit = {**changed, "collect_time": "2026-11-06T10:20:00"}
    _apply_vm_update(changed, unchanged_after_edit)
    later = {**unchanged_after_edit, "collect_time": "2026-11-06T10:25:00"}
    _apply_vm_update(unchanged_after_edit, later)
    assert ChangeRecord.objects.filter(inst_id=101).count() == 3
    assert ChangeRecordMirrorOutbox.objects.count() == 1
    assert OperationLog.objects.filter(app="cmdb", target_id="101").count() == 1


def _apply_vm_update(old, stored, *, heartbeat=False):
    from apps.cmdb.collection.common import Management

    item = {"inst_info": stored}
    if heartbeat:
        item["heartbeat"] = True
    management = SimpleNamespace(model_id="vmware_vm", task_name="VMware虚拟机采集", old_data=[old])
    management._persist_collected_tag_options = lambda result: None
    Management._after_instances_applied(
        management,
        {
            "add": {"success": [], "failed": []},
            "update": {"success": [item], "failed": []},
            "delete": {"success": [], "failed": []},
        },
    )


def test_collect_omits_blank_task_and_falls_back_to_ip_or_id():
    write_collect_instance_change_records(
        SimpleNamespace(task_name="   "),
        {
            "add": {
                "success": [
                    {"inst_info": {"_id": 11, "model_id": "host", "ip_addr": "10.1.1.1"}},
                    {"inst_info": {"_id": 12, "model_id": "host"}},
                    {"inst_info": {"model_id": "host", "inst_name": "no-id"}},
                ]
            },
            "update": {"success": []},
            "delete": {"success": []},
        },
    )

    assert _message(11) == "自动采集新增实例. 模型:host 实例:10.1.1.1"
    assert _message(12) == "自动采集新增实例. 模型:host 实例:12"
    assert ChangeRecord.objects.count() == 2


def test_instance_create_persists_source_and_skips_silent_write(fake_graph, quiet_instance_writes):
    names = {
        "plain": 101,
        "manual": 102,
        "sync": 103,
        "blank": 104,
        "silent": 105,
    }

    def create_entity(_label, info, *_args, **_kwargs):
        return {
            "_id": names[info["inst_name"]],
            "model_id": "host",
            "inst_name": info["inst_name"],
            "inst_uuid": info["inst_uuid"],
        }

    fake_graph(MODULE, query_entity=([], 0), create_entity=create_entity)

    InstanceManage.instance_create("host", {"inst_name": "plain"}, "admin", allowed_org_ids=[1])
    InstanceManage.instance_create("host", {"inst_name": "manual"}, "admin", allowed_org_ids=[1], audit_source="手动")
    InstanceManage.instance_create("host", {"inst_name": "sync"}, "system", allowed_org_ids=[1], audit_source="节点同步")
    InstanceManage.instance_create("host", {"inst_name": "blank"}, "admin", allowed_org_ids=[1], audit_source="   ")
    before = ChangeRecord.objects.count()
    silent = InstanceManage.instance_create(
        "host",
        {"inst_name": "silent"},
        "admin",
        allowed_org_ids=[1],
        record_change=False,
        audit_source="手动",
    )

    assert _message(101) == "创建模型实例. 模型:host 实例:plain"
    assert _message(102) == "创建模型实例. 来源:手动 模型:host 实例:manual"
    assert _message(103) == "创建模型实例. 来源:节点同步 模型:host 实例:sync"
    assert _message(104) == "创建模型实例. 模型:host 实例:blank"
    assert ChangeRecord.objects.get(inst_id=103).operator == "system"
    assert ChangeRecord.objects.get(inst_id=103).scenario == ORDINARY_ATTRIBUTE_CHANGE
    assert ChangeRecord.objects.count() == before
    assert silent["inst_name"] == "silent"
    assert not ChangeRecord.objects.filter(message__contains="silent").exists()


def test_instance_update_persists_model_name_and_renamed_instance(fake_graph, quiet_instance_writes):
    fake_graph(
        MODULE,
        query_entity_by_id={
            "_id": 5,
            "inst_uuid": HOST_UUID,
            "model_id": "host",
            "inst_name": "before",
            "organization": [1],
        },
        query_entity=([], 0),
        set_entity_properties=[
            {
                "_id": 5,
                "inst_uuid": HOST_UUID,
                "model_id": "host",
                "inst_name": "after",
                "organization": [1],
            }
        ],
    )

    InstanceManage.instance_update([{"id": 1}], ["admin"], 5, {"inst_name": "after"}, "admin", audit_source="手动")

    record = ChangeRecord.objects.get(inst_id=5)
    assert record.type == UPDATE_INST
    assert record.message == "修改模型实例属性. 来源:手动 模型:主机 实例:after"
    assert record.operator == "admin"
    assert record.model_object == OPERATOR_INSTANCE


def test_batch_writes_persist_source_model_name_and_ip_fallback(fake_graph, quiet_instance_writes):
    catalog = {
        7: {"_id": 7, "inst_uuid": HOST_UUID, "model_id": "host", "inst_name": "keep", "organization": [1]},
        8: {"_id": 8, "inst_uuid": HOST_UUID, "model_id": "host", "ip_addr": "10.9.9.9", "organization": [1]},
    }

    def query_entity_by_ids(inst_ids):
        return [catalog[inst_id] for inst_id in inst_ids]

    fake_graph(
        MODULE,
        query_entity=([], 0),
        query_entity_by_ids=query_entity_by_ids,
        batch_create_entity=[
            {"success": True, "data": {"_id": 6, "ip_addr": "10.8.8.8", "inst_uuid": HOST_UUID}},
        ],
        set_entity_properties=[
            {"_id": 7, "inst_uuid": HOST_UUID, "model_id": "host", "inst_name": "keep", "organization": [1], "memo": "x"},
        ],
    )

    created = InstanceManage.instance_batch_create(
        "host",
        [{"inst_name": "ignored-by-graph", "ip_addr": "10.8.8.8"}],
        "openapi",
        allowed_org_ids=[1],
        audit_source="OpenAPI",
    )
    InstanceManage.batch_instance_update(
        [{"id": 1}],
        ["admin"],
        [7],
        {"memo": "x"},
        "admin",
        audit_source="OpenAPI",
    )
    InstanceManage.instance_batch_delete([{"id": 1}], ["admin"], [8], "admin", audit_source="手动")

    assert created[0]["_id"] == 6
    assert _message(6) == "创建模型实例. 来源:OpenAPI 模型:host 实例:10.8.8.8"
    assert _message(7) == "修改模型实例属性. 来源:OpenAPI 模型:主机 实例:keep"
    assert _message(8) == "删除模型实例. 来源:手动 模型:主机 实例:10.9.9.9"
    assert ChangeRecord.objects.get(inst_id=6).type == CREATE_INST
    assert ChangeRecord.objects.get(inst_id=7).type == UPDATE_INST
    assert ChangeRecord.objects.get(inst_id=8).type == DELETE_INST


def test_module_ingest_persists_node_and_monitor_sources(fake_graph, quiet_instance_writes):
    fake_graph(
        MODULE,
        query_entity=([], 0),
        create_entity={
            "_id": 21,
            "model_id": "host",
            "inst_name": "mon-host",
            "inst_uuid": HOST_UUID,
        },
    )
    CmdbModuleIngestService._create_instance(
        "host",
        {"inst_name": "mon-host", "ip_addr": "10.3.3.3"},
        update_fields=("inst_name", "ip_addr"),
        operator="system",
        allowed_org_ids=[1],
        audit_source="监控接入",
    )
    assert _message(21) == "创建模型实例. 来源:监控接入 模型:host 实例:mon-host"

    fake_graph(
        MODULE,
        query_entity_by_id={
            "_id": 22,
            "inst_uuid": HOST_UUID,
            "model_id": "host",
            "inst_name": "node-host",
            "ip_addr": "10.0.0.1",
            "organization": [1],
        },
        query_entity=([], 0),
        set_entity_properties=[
            {
                "_id": 22,
                "inst_uuid": HOST_UUID,
                "model_id": "host",
                "inst_name": "node-host",
                "ip_addr": "10.0.0.9",
                "organization": [1],
            }
        ],
    )
    CmdbModuleIngestService._update_instance(
        {"_id": 22, "model_id": "host", "inst_name": "node-host", "ip_addr": "10.0.0.1", "organization": [1]},
        {"inst_name": "node-host", "ip_addr": "10.0.0.9", "organization": [1]},
        update_fields=("inst_name", "ip_addr", "organization"),
        operator="system",
        allowed_org_ids=[1],
        audit_source="节点接入",
    )
    record = ChangeRecord.objects.get(inst_id=22)
    assert record.message == "修改模型实例属性. 来源:节点接入 模型:主机 实例:node-host"
    assert record.operator == "system"


def test_outbox_persists_manual_import_and_plain_sentences():
    cases = [
        (
            "instance.create",
            "manual-op",
            {"audit_source": "手动"},
            {"_id": 31, "model_id": "host", "inst_name": "ui-host"},
            "创建模型实例. 来源:手动 模型:host 实例:ui-host",
        ),
        (
            "instance.update",
            "import-op",
            {"audit_source": "导入"},
            {"_id": 32, "model_id": "host", "inst_name": "moved"},
            "修改模型实例. 来源:导入 模型:host 实例:moved",
        ),
        ("instance.create", "plain-op", {}, {"_id": 33, "model_id": "host", "ip_addr": "10.4.4.4"}, "创建模型实例. 模型:host 实例:10.4.4.4"),
    ]
    for action, key, payload, result, expected in cases:
        started = OperationService.start(
            operator="alice",
            idempotency_key=key,
            action=action,
            target={"model_id": "host"},
            request_payload={"inst_name": result.get("inst_name", "")},
            event_context=payload,
        )
        OperationService.execute_graph(
            started.operation,
            graph_write=lambda _operation_id, result=result: result,
            events=OperationService.events_for_operation(started.operation),
        )
        event = CmdbOperationOutbox.objects.get(operation=started.operation, event_type="change_record")
        assert OperationService.consume_outbox(event.event_id, owner_token=key) is True
        record = ChangeRecord.objects.get(operation_event_id=event.event_id)
        assert record.message == expected
        assert record.operator == "alice"
        assert record.model_object == OPERATOR_INSTANCE
        assert record.inst_id == result["_id"]


def test_transfer_import_persists_import_source(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.transfer_import.load_attribute_snapshot", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        "apps.cmdb.services.transfer_import.InstanceManage.instance_create",
        lambda *_args, **_kwargs: {"_id": 41, "model_id": "host", "inst_name": "imported-host"},
    )
    task = SimpleNamespace(pk=7, model_id="host")
    context = SimpleNamespace(actor=SimpleNamespace(username="importer", roles=[]), teams=[1])

    result, failure = TransferImport._execute_instance_write(
        task,
        context,
        {"editable": {}},
        None,
        {"model_id": "host", "inst_name": "imported-host"},
        1,
    )

    assert failure is None
    assert result["inst_name"] == "imported-host"
    event = CmdbOperationOutbox.objects.get(operation__idempotency_key="transfer:7:1", event_type="change_record")
    assert event.payload["audit_source"] == "导入"
    assert OperationService.consume_outbox(event.event_id, owner_token="transfer-audit") is True
    record = ChangeRecord.objects.get(operation_event_id=event.event_id)
    assert record.message == "创建模型实例. 来源:导入 模型:host 实例:imported-host"
    assert record.operator == "importer"


def test_pc_delete_audit_persists_task_name_and_snapshot():
    PCSnapshotReconciler(SimpleNamespace(name="终端软件采集", id=9))._write_delete_audit(
        [{"_id": 51, "model_id": "pc_software", "inst_name": "chrome"}],
        "snap-1",
    )
    PCSnapshotReconciler(SimpleNamespace(name="", id=42))._write_delete_audit(
        [{"_id": 52, "model_id": "pc_software", "inst_name": "legacy"}],
        "snap-2",
    )

    named = ChangeRecord.objects.get(inst_id=51)
    assert named.type == DELETE_INST
    assert named.scenario == COLLECT_AUTOMATION_CHANGE
    assert named.operator == "system"
    assert named.message == "自动采集删除实例. 任务:终端软件采集 模型:pc_software 实例:chrome 快照:snap-1"
    assert _message(52) == "自动采集删除实例. 任务:42 模型:pc_software 实例:legacy 快照:snap-2"
