"""VC 任务保存和采集 runner 的归属行为；真实 ORM、有状态图库边界。"""
import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.cmdb.collection.collect_tasks.registry import RegisteredCollect
from apps.cmdb.models import CollectModels

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class Graph:
    def __init__(self):
        self.rows = {}
        self.writes = []
        self.fail_root = False
        self.edges = set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def insert(self, name, model="vmware_vc", owner="", **extra):
        row = dict(_id=len(self.rows) + 1, inst_uuid=str(uuid4()), model_id=model, inst_name=name, collect_task=owner, organization=[1], **extra)
        self.rows[row["_id"]] = row
        return copy.deepcopy(row)

    def query_entity(self, label, params, **kwargs):
        rows = list(self.rows.values())
        for p in params:
            field, value, kind = p["field"], p["value"], p["type"]
            if kind.endswith("[]"):
                rows = [r for r in rows if r.get(field) in value]
            else:
                rows = [r for r in rows if r.get(field) == value]
        return copy.deepcopy(rows), len(rows)

    def query_entity_by_inst_uuid(self, value):
        return next((copy.deepcopy(r) for r in self.rows.values() if r["inst_uuid"] == value), {})

    def query_entity_by_inst_uuids(self, values):
        return [copy.deepcopy(r) for r in self.rows.values() if r["inst_uuid"] in values]

    def set_entity_properties(self, label, ids, info, *args):
        if self.fail_root and info["model_id"] == "vmware_vc":
            raise RuntimeError("root write failed")
        from apps.cmdb.graph.falkordb import FalkorDBClient

        info = FalkorDBClient.get_editable_attr(None, info, args[0]["editable"])
        self.writes.append(("update", ids[:]))
        for pk in ids:
            self.rows[pk].update(copy.deepcopy(info))
        return [copy.deepcopy(self.rows[pk]) for pk in ids]

    def create_entity(self, label, info, *args):
        self.writes.append(("create", info["inst_name"]))
        row = copy.deepcopy(info)
        row["_id"] = max(self.rows, default=0) + 1
        self.rows[row["_id"]] = row
        return copy.deepcopy(row)

    def create_edge(self, label, src, src_label, dst, dst_label, info, unique):
        self.edges.add((src, dst, info[unique]))

    def batch_update_node_properties(self, label, ids, props):
        for pk in ids:
            self.rows[pk].update(props)

    def detach_delete_entity(self, label, pk):
        self.writes.append(("delete", pk))
        del self.rows[pk]


@pytest.fixture
def graph(monkeypatch):
    from apps.cmdb.collection import common, metrics_cannula
    from apps.cmdb.graph.drivers import graph_client
    from apps.cmdb.services import collect_service, vmware_collection_scope

    g = Graph()
    for module in (common, metrics_cannula, graph_client, collect_service, vmware_collection_scope):
        monkeypatch.setattr(module, "GraphClient", lambda **kw: g)
    monkeypatch.setattr(
        common.ModelManage,
        "search_model_attr",
        lambda model: [
            dict(attr_id="inst_name", attr_name="实例名", is_only=True, is_required=True),
            dict(attr_id="organization", attr_name="组织", is_required=True),
            *[
                dict(attr_id=k, attr_name=k)
                for k in ("model_id", "inst_uuid", "collect_task", "auto_collect", "collect_time", "vc_version", "self_vc", "vcpus")
            ],
        ],
    )
    monkeypatch.setattr(common, "write_collect_instance_change_records", lambda *a, **kw: None)
    monkeypatch.setattr("apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile", lambda *a, **kw: None)
    monkeypatch.setattr("apps.cmdb.services.auto_relation_reconcile.schedule_incoming_rule_full_sync_by_model_ids", lambda *a, **kw: None)
    return g


def task(root, name, **extra):
    values = dict(
        name=name,
        model_id="vmware_vc",
        task_type="vm",
        driver_type="protocol",
        team=[1],
        instances=[{k: v for k, v in root.items() if k not in ("_id", "collect_task")}],
        access_point=[{"id": "node-1", "cloud": 1}],
        credential={"port": 443},
        is_interval=False,
        data_cleanup_strategy="no_cleanup",
    )
    values.update(extra)
    return CollectModels.objects.create(**values)


def metrics(root_name, vm_name="vm[vm-1]"):
    return {"vmware_vc": [{"inst_name": root_name, "vc_version": "8"}], "vmware_vm": [{"inst_name": vm_name, "self_vc": root_name, "vcpus": 4}]}


def run(t, data):
    return RegisteredCollect(t.id, default_metrics=copy.deepcopy(data), task=t).run()[1]


def test_existing_vc_owner_blocks_alias_task_before_any_write(graph):
    original = graph.insert("original VC", ip_addr="192.0.2.10")
    alias = graph.insert("alias VC", ip_addr="192.0.2.10")
    old = task(original, "old")
    graph.insert("vm[vm-1]", "vmware_vm", str(old.id))
    new = task(alias, "new")
    before = copy.deepcopy(graph.rows)
    result = run(new, metrics(alias["inst_name"]))
    assert graph.rows == before
    assert graph.writes == []
    assert result["add"] == []
    assert len(result["update"]) == 2
    assert all(r["_status"] == "failed" and "其他采集任务" in r["_error"] for r in result["update"])


def test_task_save_rejects_existing_alias_target(graph, monkeypatch):
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *a, **kw: {"team": [1]})
    from apps.cmdb.serializers.collect_serializer import CollectModelSerializer

    root = graph.insert("original", ip_addr="192.0.2.10")
    alias = graph.insert("alias", ip_addr="192.0.2.10")
    task(root, "old")
    duplicate = task(alias, "duplicate", credential={"port": 443, "username": "test", "password": "test-only"})
    serializer = CollectModelSerializer(
        duplicate,
        data={"name": "edited duplicate"},
        partial=True,
        context={"request": SimpleNamespace(user=SimpleNamespace(username="test"), COOKIES={})},
    )
    assert not serializer.is_valid()
    assert "其他采集任务" in str(serializer.errors)


def test_original_owner_claims_root_even_with_existing_duplicate(graph):
    root = graph.insert("original", ip_addr="192.0.2.10")
    alias = graph.insert("alias", ip_addr="192.0.2.10")
    old = task(root, "old")
    graph.insert("vm[vm-1]", "vmware_vm", str(old.id))
    task(alias, "duplicate")
    result = run(old, metrics(root["inst_name"]))
    assert result["add"] == []
    assert len(result["update"]) == 2
    assert all(r["_status"] == "success" for r in result["update"])
    assert graph.rows[root["_id"]]["collect_task"] == str(old.id)
    assert graph.rows[root["_id"]]["inst_uuid"] == root["inst_uuid"]
    assert graph.rows[alias["_id"]] == alias


def test_root_rename_uses_uuid_and_updates_child_reference(graph):
    root = graph.insert("old name", ip_addr="192.0.2.10")
    t = task(root, "task")
    graph.rows[root["_id"]]["inst_name"] = "new name"
    result = run(t, metrics("old name"))
    assert len(result["add"]) == 1
    assert result["add"][0]["model_id"] == "vmware_vm"
    assert graph.rows[root["_id"]]["inst_name"] == "new name"
    assert graph.rows[root["_id"]]["inst_uuid"] == root["inst_uuid"]
    assert graph.rows[2]["self_vc"] == "new name"
    assert graph.writes[0] == ("update", [root["_id"]])


def test_root_failure_stops_children_and_retains_all_existing_data(graph):
    root = graph.insert("root", ip_addr="192.0.2.10")
    t = task(root, "task")
    before = copy.deepcopy(graph.rows)
    graph.fail_root = True
    data = metrics("root")
    data = {"vmware_vm": data["vmware_vm"], "vmware_vc": data["vmware_vc"]}
    result = run(t, data)
    assert graph.rows == before
    assert graph.writes == []
    assert result["add"] == []
    assert len(result["update"]) == 2
    assert all(r["_status"] == "failed" for r in result["update"])
    assert any("根资产更新失败" in r["_error"] for r in result["update"])


def test_delete_old_task_then_alias_target_reuses_original_root_and_vm(graph):
    from apps.cmdb.services.collect_service import CollectModelService

    root = graph.insert("original", ip_addr="192.0.2.10")
    old = task(root, "old")
    run(old, metrics("original"))
    root_uuid = graph.rows[1]["inst_uuid"]
    vm_uuid = graph.rows[2]["inst_uuid"]
    CollectModelService.clear_instance_collect_task(old.id)
    old.delete()
    assert all(row["collect_task"] == "" for row in graph.rows.values())
    alias = graph.insert("alias", ip_addr="192.0.2.10")
    new = task(alias, "new")
    result = run(new, metrics("alias"))
    assert result["add"] == []
    assert len(result["update"]) == 2
    assert len(graph.rows) == 3
    assert graph.rows[1]["inst_uuid"] == root_uuid
    assert graph.rows[2]["inst_uuid"] == vm_uuid
    assert graph.rows[1]["collect_task"] == graph.rows[2]["collect_task"] == str(new.id)
    assert graph.rows[2]["self_vc"] == "original"
    assert graph.rows[alias["_id"]] == alias
    result = run(new, metrics("alias"))
    assert result["add"] == [] and len(graph.rows) == 3


def test_multiple_owners_reject_entire_snapshot(graph):
    root = graph.insert("root", ip_addr="192.0.2.10")
    alias = graph.insert("alias", ip_addr="192.0.2.10")
    a = task(root, "a")
    b = task(alias, "b")
    graph.rows[root["_id"]]["collect_task"] = str(a.id)
    graph.insert("vm[vm-1]", "vmware_vm", str(b.id))
    before = copy.deepcopy(graph.rows)
    result = run(a, metrics("root"))
    assert graph.rows == before and graph.writes == []
    assert all("混合归属" in r["_error"] for r in result["update"])


def test_missing_root_sample_does_not_write_children(graph):
    root = graph.insert("root", ip_addr="192.0.2.10")
    t = task(root, "task")
    result = run(t, {"vmware_vm": [{"inst_name": "vm[vm-1]"}]})
    assert graph.writes == []
    assert "缺少" in result["update"][0]["_error"]


@pytest.mark.parametrize("change", [dict(access_point=[{"id": "node-2", "cloud": 2}]), dict(credential={"port": 8443})])
def test_distinct_network_or_port_is_not_same_vc(graph, change):
    root = graph.insert("first", ip_addr="192.0.2.10")
    alias = graph.insert("second", ip_addr="192.0.2.10")
    task(root, "first")
    t = task(alias, "second", **change)
    result = run(t, metrics("second"))
    assert all(r["_status"] == "success" for r in result["update"])
    assert graph.rows[alias["_id"]]["collect_task"] == str(t.id)
    assert graph.rows[root["_id"]] == root


def test_immediate_cleanup_never_deletes_another_existing_vc_root(graph):
    root = graph.insert("root", ip_addr="192.0.2.10")
    t = task(root, "task", data_cleanup_strategy="immediately")
    duplicate = graph.insert("historical duplicate", owner=str(t.id), ip_addr="192.0.2.10")
    foreign = graph.insert("other range", "vmware_vm", owner="999")
    orphan = graph.insert("unowned outside snapshot", "vmware_vm")
    run(t, metrics("root"))
    assert graph.rows[duplicate["_id"]] == duplicate
    assert graph.rows[foreign["_id"]] == foreign
    assert graph.rows[orphan["_id"]] == orphan
    assert not any(op[0] == "delete" for op in graph.writes)


def serializer(t, data, monkeypatch):
    from apps.cmdb.serializers.collect_serializer import CollectModelSerializer
    from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil

    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *a, **kw: {"team": [1]})
    monkeypatch.setattr(CmdbRulesFormatUtil, "format_user_groups_permissions", lambda *a, **kw: {})
    return CollectModelSerializer(t, data=data, partial=True, context={"request": SimpleNamespace(user=SimpleNamespace(username="test"), COOKIES={})})


def test_original_owner_can_save_despite_legacy_duplicate(graph, monkeypatch):
    root = graph.insert("original", ip_addr="192.0.2.10")
    alias = graph.insert("alias", ip_addr="192.0.2.10")
    old = task(root, "old")
    graph.insert("vm[vm-1]", "vmware_vm", old.id)
    task(alias, "new")
    s = serializer(old, {"name": "renamed old"}, monkeypatch)
    assert s.is_valid(), s.errors
    s.save()
    old.refresh_from_db()
    assert old.name == "renamed old"
    assert graph.writes == []


def test_new_vc_task_create_rejects_same_endpoint_with_other_root(graph, monkeypatch):
    from apps.cmdb.services import instance as instance_module

    monkeypatch.setattr(instance_module, "GraphClient", lambda **kw: graph)
    root = graph.insert("original", ip_addr="192.0.2.10")
    alias = graph.insert("alias", ip_addr="192.0.2.10")
    task(root, "old")
    s = serializer(
        None,
        dict(
            name="new",
            model_id="vmware_vc",
            task_type="vm",
            driver_type="protocol",
            team=[1],
            instances=[{"inst_uuid": alias["inst_uuid"], "ip_addr": "forged.example"}],
            access_point=[{"id": "node-1", "cloud": 1}],
            credential={"port": 443},
        ),
        monkeypatch,
    )
    assert not s.is_valid()
    assert "其他采集任务" in str(s.errors)
    assert CollectModels.objects.count() == 1
    assert graph.writes == []


def test_task_edit_cannot_move_owned_task_to_another_reserved_vc(graph, monkeypatch):
    from apps.cmdb.services import instance as instance_module

    monkeypatch.setattr(instance_module, "GraphClient", lambda **kw: graph)
    root = graph.insert("original", ip_addr="192.0.2.10")
    other = graph.insert("other", ip_addr="192.0.2.20")
    old = task(root, "old")
    graph.insert("vm[vm-1]", "vmware_vm", str(old.id))
    task(other, "other")
    s = serializer(old, {"instances": [{"inst_uuid": other["inst_uuid"]}]}, monkeypatch)
    assert not s.is_valid()
    assert "其他采集任务" in str(s.errors)


def test_legacy_hostname_case_and_trailing_dot_cannot_bypass_duplicate_check(graph, monkeypatch):
    root = graph.insert("original", ip_addr="VC.Example.")
    alias = graph.insert("alias", ip_addr="vc.example")
    task(root, "old")
    new = task(alias, "new")
    s = serializer(new, {"name": "edited"}, monkeypatch)
    assert not s.is_valid()
    assert "其他采集任务" in str(s.errors)


def test_cross_organization_orphan_root_cannot_be_adopted(graph):
    root = graph.insert("root", ip_addr="192.0.2.10")
    t = task(root, "task")
    graph.rows[root["_id"]]["organization"] = [2]
    before = copy.deepcopy(graph.rows)
    result = run(t, metrics("root"))
    assert graph.rows == before and graph.writes == []
    assert all("组织范围" in r["_error"] for r in result["update"])


def test_other_owned_child_blocks_free_root_even_without_peer_configuration(graph):
    root = graph.insert("root", ip_addr="192.0.2.10")
    t = task(root, "task")
    graph.insert("vm[vm-1]", "vmware_vm", "999")
    before = copy.deepcopy(graph.rows)
    result = run(t, metrics("root"))
    assert graph.rows == before and graph.writes == []
    assert all("其他采集任务" in r["_error"] for r in result["update"])


def test_real_plugin_replacement_preserves_root_child_uuids_and_relationships(graph, monkeypatch):
    from apps.cmdb.services.collect_service import CollectModelService

    class Collection:
        def query(self, sql, **kwargs):
            samples = [
                ("vmware_vc", {"inst_name": "remote vc", "vc_version": "8"}),
                ("vmware_ds", {"inst_name": "ds[datastore-1]", "resource_id": "datastore-1"}),
                ("vmware_esxi", {"inst_name": "host[host-1]", "resource_id": "host-1", "vmware_ds": "datastore-1"}),
                ("vmware_vm", {"inst_name": "vm[vm-1]", "resource_id": "vm-1", "vmware_ds": "datastore-1", "vmware_esxi": "host-1"}),
            ]
            return {
                "data": {
                    "result": [
                        {"metric": {"__name__": model + "_info_gauge", "collect_status": "success", **labels}, "value": [9999999999, "1"]}
                        for model, labels in samples
                    ]
                }
            }

    monkeypatch.setattr("apps.cmdb.collection.collect_plugin.base.Collection", Collection)
    root = graph.insert("original", ip_addr="192.0.2.10")
    old = task(root, "old")
    first = RegisteredCollect(old.id, task=old).run()[1]
    assert len(first["add"]) == 3 and len(first["update"]) == 1
    assert all(row["_status"] == "success" for row in first["add"] + first["update"])
    before = {pk: row["inst_uuid"] for pk, row in graph.rows.items()}
    edges = set(graph.edges)
    assert edges == {
        (3, 1, "vmware_esxi_group_vmware_vc"),
        (3, 2, "vmware_esxi_connect_vmware_ds"),
        (4, 3, "vmware_vm_run_vmware_esxi"),
        (4, 2, "vmware_vm_connect_vmware_ds"),
    }
    CollectModelService.clear_instance_collect_task(old.id)
    old.delete()
    alias = graph.insert("alias", ip_addr="192.0.2.10")
    new = task(alias, "new")
    second = RegisteredCollect(new.id, task=new).run()[1]
    assert second["add"] == [] and len(second["update"]) == 4
    assert all(row["_status"] == "success" for row in second["update"])
    assert {pk: graph.rows[pk]["inst_uuid"] for pk in before} == before
    assert all(graph.rows[pk]["collect_task"] == str(new.id) for pk in before)
    assert graph.edges == edges
    assert graph.rows[alias["_id"]] == alias

    # 实际 worker 持久化冲突详情，界面读取的摘要不能再报告“新增失败/实例名已存在”。
    from apps.cmdb.constants.constants import CollectRunStatusType
    from apps.cmdb.tasks.celery_tasks import sync_collect_task

    duplicate = task(alias, "blocked")
    before_rows = copy.deepcopy(graph.rows)
    graph.writes.clear()
    sync_collect_task(duplicate.id, execution_id="vc-conflict-test")
    duplicate.refresh_from_db()
    assert duplicate.exec_status == CollectRunStatusType.ERROR
    assert duplicate.collect_digest["add"] == 0
    assert duplicate.collect_digest["update_error"] == 4
    assert all("其他采集任务" in row["_error"] for row in duplicate.format_data["update"])
    assert graph.rows == before_rows and graph.writes == []


def test_service_create_rejects_duplicate_before_creating_task_or_pushing_config(graph, monkeypatch):
    from rest_framework.exceptions import ValidationError

    from apps.cmdb.services import instance as instance_module
    from apps.cmdb.services.collect_service import CollectModelService

    monkeypatch.setattr(instance_module, "GraphClient", lambda **kw: graph)
    root = graph.insert("old", ip_addr="192.0.2.10")
    alias = graph.insert("new", ip_addr="192.0.2.10")
    task(root, "old")
    request = SimpleNamespace(
        data=dict(
            name="new",
            task_type="vm",
            model_id="vmware_vc",
            driver_type="protocol",
            timeout=60,
            input_method=0,
            team=[1],
            scan_cycle={"value_type": "cycle", "value": "30"},
            instances=[{"inst_uuid": alias["inst_uuid"]}],
            access_point=[{"id": "node-1", "cloud": 1}],
            credential=[{"port": 443, "username": "test", "password": "test-only"}],
        )
    )
    view = SimpleNamespace(
        get_serializer=lambda **kw: serializer(None, kw["data"], monkeypatch),
        perform_create=lambda s: pytest.fail("duplicate task must not be saved"),
    )
    with pytest.raises(ValidationError, match="其他采集任务"):
        CollectModelService.create(request, view)
    assert CollectModels.objects.count() == 1
    assert graph.writes == []


def test_uncollected_duplicate_tasks_require_resolution_without_claiming_root(graph):
    root = graph.insert("old", ip_addr="192.0.2.10")
    alias = graph.insert("new", ip_addr="192.0.2.10")
    task(root, "old")
    new = task(alias, "new")
    result = run(new, metrics("new"))
    assert graph.writes == []
    assert all("无法确定唯一归属" in row["_error"] for row in result["update"])


def test_legacy_ipv6_spelling_does_not_create_a_second_vc_task(graph, monkeypatch):
    root = graph.insert("old", ip_addr="2001:0db8:0000:0000:0000:0000:0000:0001")
    alias = graph.insert("new", ip_addr="2001:db8::1")
    task(root, "old")
    new = task(alias, "new")
    s = serializer(new, {"name": "edited"}, monkeypatch)
    assert not s.is_valid()
    assert "其他采集任务" in str(s.errors)
