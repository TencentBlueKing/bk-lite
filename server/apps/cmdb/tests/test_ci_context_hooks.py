"""图写入成功后登记 ci_context 重算。登记失败不得回滚图写入。"""

import logging

import pytest

from apps.cmdb.models.ci_context import CmdbCiContextPending
from apps.cmdb.services.ci_context import record_association_ci_context, record_instance_field_ci_context, record_instances_deleted_ci_context
from apps.cmdb.services.instance import InstanceManage

pytestmark = pytest.mark.django_db

MODULE = "apps.cmdb.services.instance"
SRC_UUID = "11111111-1111-4111-8111-111111111111"
DST_UUID = "22222222-2222-4222-8222-222222222222"
HOST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


def _pending():
    rows = list(CmdbCiContextPending.objects.all())
    return {
        "roots": sorted(row.root_uuid for row in rows if row.root_uuid),
        "cis": sorted(row.ci_uuid for row in rows if row.ci_uuid),
        "rules": sorted(row.model_asst_id for row in rows if row.model_asst_id),
    }


def test_association_from_application_schedules_root_only():
    record_association_ci_context(
        {"model_id": "application", "inst_uuid": "app-1"},
        {"model_id": "host", "inst_uuid": "host-1"},
    )

    assert _pending() == {"roots": ["app-1"], "cis": [], "rules": []}


def test_association_between_non_applications_schedules_both_cis():
    record_association_ci_context(
        {"model_id": "host", "inst_uuid": "host-1"},
        {"model_id": "mysql", "inst_uuid": "mysql-1"},
    )

    assert _pending() == {"roots": [], "cis": ["host-1", "mysql-1"], "rules": []}


def test_association_to_application_schedules_application_root():
    record_association_ci_context(
        {"model_id": "system", "inst_uuid": "sys-1"},
        {"model_id": "application", "inst_uuid": "app-1"},
    )

    assert _pending() == {"roots": ["app-1"], "cis": [], "rules": []}


def test_association_with_missing_endpoint_does_not_crash():
    record_association_ci_context(None, {})
    record_association_ci_context({"model_id": "host"}, {"inst_uuid": "  "})
    record_association_ci_context({"model_id": "application"}, {"model_id": "host", "inst_uuid": "host-1"})

    assert CmdbCiContextPending.objects.count() == 0


def test_instance_field_on_host_schedules_ci_only():
    record_instance_field_ci_context({"model_id": "host", "inst_uuid": "host-1"})

    assert _pending() == {"roots": [], "cis": ["host-1"], "rules": []}


def test_instance_field_on_application_schedules_root_and_ci():
    record_instance_field_ci_context({"model_id": "application", "inst_uuid": "app-1"})

    assert _pending() == {"roots": ["app-1"], "cis": ["app-1"], "rules": []}


def test_deleted_instances_schedule_host_ci_and_application_root():
    record_instances_deleted_ci_context(
        [
            {"model_id": "host", "inst_uuid": "host-1"},
            {"model_id": "application", "inst_uuid": "app-1"},
        ]
    )

    assert _pending() == {"roots": ["app-1"], "cis": ["app-1", "host-1"], "rules": []}


def test_helpers_swallow_schedule_errors(monkeypatch, caplog):
    def boom(**_kwargs):
        raise RuntimeError("pending-down")

    monkeypatch.setattr("apps.cmdb.services.ci_context.schedule_ci_context_pending", boom)
    caplog.set_level(logging.ERROR, logger="cmdb")

    assert record_association_ci_context({"model_id": "host", "inst_uuid": "host-1"}, {"model_id": "mysql", "inst_uuid": "mysql-1"}) is None
    assert record_instance_field_ci_context({"model_id": "host", "inst_uuid": "host-1"}) is None
    assert record_instances_deleted_ci_context([{"model_id": "host", "inst_uuid": "host-1"}]) is None

    records = [record for record in caplog.records if record.name == "cmdb" and record.levelno >= logging.ERROR]
    assert [record.getMessage() for record in records] == [
        "failed to record association ci_context",
        "failed to record instance field ci_context",
        "failed to record deleted instance ci_context",
    ]
    assert all(record.exc_info and record.exc_info[0] is RuntimeError for record in records)
    assert CmdbCiContextPending.objects.count() == 0


@pytest.fixture
def quiet_instance_writes(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile",
        lambda ids: None,
    )
    monkeypatch.setattr(f"{MODULE}.schedule_instance_auto_relation_reconcile", lambda ids: None)
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_incoming_rule_full_sync_by_model_ids",
        lambda model_ids: None,
    )
    monkeypatch.setattr(
        f"{MODULE}.InstanceManage._build_unique_rule_check_attr_map",
        lambda model_id, attrs, for_update=False: {"is_only": {}, "is_required": {}, "unique_rules": [], "attrs_by_id": {}},
    )
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda model_id: {"model_id": model_id, "model_name": "主机", "attrs": "[]", "_id": 1},
    )
    monkeypatch.setattr(f"{MODULE}.InstanceManage.check_instances_permission", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "apps.cmdb.services.module_push.CmdbToMonitorPushService.best_effort_notify_on_delete",
        lambda *args, **kwargs: None,
    )


class _Graph:
    def __init__(self, **methods):
        self._methods = methods

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        method = self._methods.get(name)
        if method is None:
            raise AttributeError(name)
        return method


def test_create_by_uuid_already_exists_does_not_record(monkeypatch):
    calls = []
    monkeypatch.setattr(f"{MODULE}.record_association_ci_context", lambda src, dst: calls.append((src, dst)))
    monkeypatch.setattr(
        InstanceManage,
        "query_entity_by_uuid",
        staticmethod(lambda inst_uuid: {"_id": 1, "inst_uuid": inst_uuid, "model_id": "host"}),
    )
    monkeypatch.setattr(
        InstanceManage,
        "_association_edges_by_business_key",
        staticmethod(lambda **kwargs: [{"edge": {"_id": 9}}]),
    )

    result = InstanceManage.instance_association_create_by_uuid(
        src_inst_uuid=SRC_UUID,
        dst_inst_uuid=DST_UUID,
        model_asst_id="host_connect_mysql",
        operator="admin",
        allow_existing=True,
    )

    assert result == {"already_exists": True}
    assert calls == []


def test_association_create_records_preloaded_endpoints(monkeypatch):
    src = {"_id": 1, "inst_uuid": SRC_UUID, "model_id": "application", "inst_name": "app"}
    dst = {"_id": 2, "inst_uuid": DST_UUID, "model_id": "host", "inst_name": "host"}
    calls = []
    monkeypatch.setattr(f"{MODULE}.record_association_ci_context", lambda left, right: calls.append((left, right)))
    monkeypatch.setattr(InstanceManage, "check_asso_mapping", staticmethod(lambda data: None))
    monkeypatch.setattr(InstanceManage, "query_entity_by_id", staticmethod(lambda inst_id: src if inst_id == 1 else dst))
    monkeypatch.setattr(
        InstanceManage,
        "instance_association_by_asso_id",
        staticmethod(lambda asso_id: {"edge": {"_id": asso_id}}),
    )
    monkeypatch.setattr(f"{MODULE}.create_change_record_by_asso", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        f"{MODULE}.GraphClient",
        lambda *args, **kwargs: _Graph(create_edge=lambda *a, **k: {"_id": 41}),
    )

    edge = InstanceManage.instance_association_create(
        {"src_inst_id": 1, "dst_inst_id": 2, "model_asst_id": "application_run_host"},
        "admin",
    )

    assert edge["_id"] == 41
    assert calls == [(src, dst)]


def test_association_delete_records_pre_delete_endpoints_after_graph_delete(monkeypatch):
    src = {"_id": 1, "inst_uuid": SRC_UUID, "model_id": "host", "inst_name": "h"}
    dst = {"_id": 2, "inst_uuid": DST_UUID, "model_id": "mysql", "inst_name": "m"}
    order = []
    calls = []

    def load(asso_id):
        order.append("load")
        return {"src": src, "dst": dst, "edge": {"_id": asso_id}}

    def delete_edge(asso_id):
        order.append("delete")

    def record(left, right):
        order.append("record")
        calls.append((left, right))

    monkeypatch.setattr(InstanceManage, "instance_association_by_asso_id", staticmethod(load))
    monkeypatch.setattr(f"{MODULE}.GraphClient", lambda *args, **kwargs: _Graph(delete_edge=delete_edge))
    monkeypatch.setattr(f"{MODULE}.record_association_ci_context", record)
    monkeypatch.setattr(f"{MODULE}.create_change_record_by_asso", lambda *args, **kwargs: None)

    InstanceManage._instance_association_delete_by_graph_id(7, "admin")

    assert order == ["load", "delete", "record"]
    assert calls == [(src, dst)]


def test_association_delete_skips_record_when_graph_delete_fails(monkeypatch):
    calls = []

    def delete_edge(asso_id):
        raise RuntimeError("graph down")

    monkeypatch.setattr(
        InstanceManage,
        "instance_association_by_asso_id",
        staticmethod(lambda asso_id: {"src": {"model_id": "host", "inst_uuid": SRC_UUID}, "dst": {"model_id": "mysql", "inst_uuid": DST_UUID}}),
    )
    monkeypatch.setattr(f"{MODULE}.GraphClient", lambda *args, **kwargs: _Graph(delete_edge=delete_edge))
    monkeypatch.setattr(f"{MODULE}.record_association_ci_context", lambda left, right: calls.append((left, right)))

    with pytest.raises(RuntimeError, match="graph down"):
        InstanceManage._instance_association_delete_by_graph_id(7, "admin")

    assert calls == []


def test_instance_update_records_ip_change_and_skips_name_only(fake_graph, quiet_instance_writes, monkeypatch):
    calls = []
    monkeypatch.setattr(f"{MODULE}.record_instance_field_ci_context", lambda instance: calls.append(instance))
    current = {
        "_id": 5,
        "inst_uuid": HOST_UUID,
        "model_id": "host",
        "inst_name": "before",
        "ip_addr": "10.0.0.1",
        "organization": [1],
    }
    renamed = {**current, "inst_name": "after"}
    fake_graph(MODULE, query_entity_by_id=current, query_entity=([], 0), set_entity_properties=[renamed])

    InstanceManage.instance_update([{"id": 1}], ["admin"], 5, {"inst_name": "after"}, "admin")

    assert calls == []

    moved = {**current, "ip_addr": "10.0.0.2"}
    fake_graph(MODULE, query_entity_by_id=current, query_entity=([], 0), set_entity_properties=[moved])

    InstanceManage.instance_update([{"id": 1}], ["admin"], 5, {"ip_addr": "10.0.0.2"}, "admin")

    assert calls == [moved]


def test_instance_batch_delete_records_loaded_instances_after_graph_delete(fake_graph, quiet_instance_writes, monkeypatch):
    inst = {"_id": 8, "inst_uuid": HOST_UUID, "model_id": "host", "inst_name": "gone", "organization": [1]}
    order = []
    seen = []

    def batch_delete_entity(*args, **kwargs):
        order.append("delete")
        return {}

    def record(instances):
        order.append("record")
        seen.append(list(instances))

    monkeypatch.setattr(f"{MODULE}.record_instances_deleted_ci_context", record)
    fake_graph(MODULE, query_entity_by_ids=lambda inst_ids: [inst], batch_delete_entity=batch_delete_entity)

    InstanceManage.instance_batch_delete([{"id": 1}], ["admin"], [8], "admin")

    assert order == ["delete", "record"]
    assert seen == [[inst]]


def test_instance_batch_delete_skips_record_when_graph_delete_fails(fake_graph, quiet_instance_writes, monkeypatch):
    inst = {"_id": 8, "inst_uuid": HOST_UUID, "model_id": "host", "inst_name": "gone", "organization": [1]}
    calls = []

    def batch_delete_entity(*args, **kwargs):
        raise RuntimeError("graph down")

    monkeypatch.setattr(f"{MODULE}.record_instances_deleted_ci_context", lambda instances: calls.append(instances))
    fake_graph(MODULE, query_entity_by_ids=lambda inst_ids: [inst], batch_delete_entity=batch_delete_entity)

    with pytest.raises(RuntimeError, match="graph down"):
        InstanceManage.instance_batch_delete([{"id": 1}], ["admin"], [8], "admin")

    assert calls == []
