"""Management（采集落库编排）单元测试。

对照 apps/cmdb/collection/common.py：
  - get_check_attr_map：按 is_only/is_required/editable 归类属性
  - format_data：按 unique_keys 构建索引
  - contrast：add/update/delete 分流 + IMMEDIATELY 清理策略
  - add_inst / update_inst / delete_inst：GraphClient 副作用、异常归入 failed、
    成功后触发自动关联调度
  - set_asso_info / setting_assos：关联落库、edge already exists 幂等成功

只在 GraphClient / ModelManage.search_model_attr / schedule_* / 变更记录 /
企业扩展这些真实边界打桩。
"""
import pydantic.root_model  # noqa: F401
import pytest

from apps.cmdb.collection import common as mod
from apps.cmdb.collection.common import Management
from apps.cmdb.constants.constants import DataCleanupStrategy

pytestmark = pytest.mark.unit


class FakeGraph:
    def __init__(self, **returns):
        self.returns = returns
        self.created_entities = []
        self.created_edges = []
        self.deleted = []
        self.set_props = []
        self.set_exist_items = []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def query_entity(self, label, conds):
        self.queries.append((label, conds))
        cb = self.returns.get("query_entity")
        if callable(cb):
            return cb(label, conds)
        return cb if cb is not None else ([], 0)

    def create_entity(self, label, info, check_attr_map, exist_items):
        if "create_entity_raises" in self.returns:
            raise self.returns["create_entity_raises"]
        ent = dict(info)
        ent["_id"] = self.returns.get("new_id", 100)
        self.created_entities.append(ent)
        return ent

    def set_entity_properties(self, label, ids, info, check_attr_map, exist_items):
        ent = dict(info)
        self.set_props.append(ent)
        self.set_exist_items.append([dict(item) for item in exist_items])
        cb = self.returns.get("set_entity_properties")
        if callable(cb):
            return cb(label, ids, info, check_attr_map, exist_items)
        return [ent]

    def detach_delete_entity(self, label, _id):
        self.deleted.append(_id)
        return {}

    def create_edge(self, *args, **kwargs):
        if "create_edge_raises" in self.returns:
            raise self.returns["create_edge_raises"]
        self.created_edges.append((args, kwargs))
        return {}


def _patch_common(monkeypatch, fake, attrs=None):
    monkeypatch.setattr(mod, "GraphClient", lambda *a, **k: fake)
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr",
        lambda model_id: attrs if attrs is not None else [],
    )
    # 关闭真实变更记录与企业扩展写入
    monkeypatch.setattr(mod, "write_collect_instance_change_records", lambda *a, **k: None)

    class _Ext:
        def on_collect_instances_applied(self, **kw):
            return None

    monkeypatch.setattr(mod, "get_collect_enterprise_extension", lambda: _Ext())
    # 关闭自动关联调度
    import apps.cmdb.services.auto_relation_reconcile as ar

    monkeypatch.setattr(ar, "schedule_instance_auto_relation_reconcile", lambda ids: None)
    monkeypatch.setattr(ar, "schedule_incoming_rule_full_sync_by_model_ids", lambda ids: None)


def _mgmt(monkeypatch, fake, old_data, new_data, **kw):
    _patch_common(monkeypatch, fake, attrs=kw.pop("attrs", None))
    return Management(
        organization=[1],
        inst_name="x",
        model_id="host",
        old_data=old_data,
        new_data=new_data,
        unique_keys=["inst_name"],
        collect_time="2026-06-24",
        task_id=kw.get("task_id", 1),
        collect_plugin=kw.get("collect_plugin"),
        data_cleanup_strategy=kw.get("data_cleanup_strategy"),
    )


# --------------------------------------------------------------------------
# get_check_attr_map
# --------------------------------------------------------------------------
def test_get_check_attr_map_classifies(monkeypatch):
    fake = FakeGraph()
    attrs = [
        {"attr_id": "name", "attr_name": "名称", "is_only": True, "is_required": True, "editable": True},
        {"attr_id": "ip", "attr_name": "IP", "is_required": True, "editable": False},
        {"attr_id": "note", "attr_name": "备注"},  # editable 默认 True
    ]
    m = _mgmt(monkeypatch, fake, [], [], attrs=attrs)
    cam = m.check_attr_map
    assert cam["is_only"] == {"name": "名称"}
    assert set(cam["is_required"]) == {"name", "ip"}
    assert set(cam["editable"]) == {"name", "note"}


# --------------------------------------------------------------------------
# format_data / contrast
# --------------------------------------------------------------------------
def test_coerce_collected_tag_turns_string_into_empty_list():
    assert Management.coerce_collected_tag({"inst_name": "a"}) == {"inst_name": "a"}
    assert Management.coerce_collected_tag({"tag": ["test:aaa"]})["tag"] == ["test:aaa"]
    assert Management.coerce_collected_tag({"tag": ""})["tag"] == []
    assert Management.coerce_collected_tag({"tag": "env:prod"})["tag"] == []


def test_contrast_rewrites_string_tag_as_list_update(monkeypatch):
    fake = FakeGraph()
    old = [{"inst_name": "a", "tag": "", "_id": 1}]
    new = [{"inst_name": "a", "tag": ""}]
    m = _mgmt(monkeypatch, fake, old, new)
    assert m.update_list[0]["tag"] == []
    assert m.update_list[0]["_id"] == 1


def test_contrast_classifies_add_and_update(monkeypatch):
    fake = FakeGraph()
    old = [{"inst_name": "a", "ip_addr": "10.0.0.1", "_id": 1}]
    new = [{"inst_name": "a", "ip_addr": "10.0.0.2"}, {"inst_name": "b"}]
    m = _mgmt(monkeypatch, fake, old, new)
    assert [i["inst_name"] for i in m.add_list] == ["b"]
    assert [i["inst_name"] for i in m.update_list] == ["a"]
    # update 项注入了既有 _id
    assert m.update_list[0]["_id"] == 1
    # 默认策略不删除
    assert m.delete_list == []


def test_contrast_routes_identical_business_fields_to_heartbeat(monkeypatch):
    fake = FakeGraph()
    old = [{"inst_name": "a", "ip_addr": "10.0.0.1", "collect_time": "old", "_id": 1}]
    new = [{"inst_name": "a", "ip_addr": "10.0.0.1"}]
    m = _mgmt(monkeypatch, fake, old, new)
    assert m.update_list == []
    assert [item["_id"] for item in m.heartbeat_list] == [1]


def test_contrast_routes_changed_business_field_to_update(monkeypatch):
    fake = FakeGraph()
    old = [{"inst_name": "a", "ip_addr": "10.0.0.1", "_id": 1}]
    new = [{"inst_name": "a", "ip_addr": "10.0.0.2"}]
    m = _mgmt(monkeypatch, fake, old, new)
    assert [item["_id"] for item in m.update_list] == [1]


def test_complete_empty_snapshot_can_delete_stale_instances(monkeypatch):
    fake = FakeGraph()

    class CompleteSnapshotPlugin:
        _MODEL_ID = "winsphere"

        @staticmethod
        def is_authoritative_snapshot(model_id):
            return True

    m = _mgmt(
        monkeypatch,
        fake,
        [{"inst_name": "stale-vm", "_id": 1}],
        [],
        collect_plugin=CompleteSnapshotPlugin(),
        data_cleanup_strategy=DataCleanupStrategy.IMMEDIATELY,
    )

    assert [item["_id"] for item in m.delete_list] == [1]
    assert m.heartbeat_list == []


def test_non_authoritative_snapshot_never_deletes_missing_instances(monkeypatch):
    fake = FakeGraph()

    class PartialSnapshotPlugin:
        _MODEL_ID = "winsphere"

        @staticmethod
        def is_authoritative_snapshot(model_id):
            return False

    m = _mgmt(
        monkeypatch,
        fake,
        [
            {"inst_name": "current-vm", "_id": 1},
            {"inst_name": "possibly-missing-vm", "_id": 2},
        ],
        [{"inst_name": "current-vm"}],
        collect_plugin=PartialSnapshotPlugin(),
        data_cleanup_strategy=DataCleanupStrategy.IMMEDIATELY,
    )

    assert m.delete_list == []


def test_contrast_ignores_old_fields_absent_from_incremental_payload(monkeypatch):
    fake = FakeGraph()
    old = [{"inst_name": "a", "ip_addr": "10.0.0.1", "note": "keep", "_id": 1}]
    new = [{"inst_name": "a", "ip_addr": "10.0.0.1"}]
    m = _mgmt(monkeypatch, fake, old, new)
    assert m.update_list == []
    assert len(m.heartbeat_list) == 1


def test_contrast_keeps_nonempty_associations_on_full_update(monkeypatch):
    fake = FakeGraph()
    old = [{"inst_name": "a", "ip_addr": "10.0.0.1", "_id": 1}]
    new = [{"inst_name": "a", "ip_addr": "10.0.0.1", "assos": [{"model_id": "host"}]}]
    m = _mgmt(monkeypatch, fake, old, new)
    assert len(m.update_list) == 1
    assert m.heartbeat_list == []


def test_contrast_immediately_cleanup_deletes_missing(monkeypatch):
    fake = FakeGraph()

    class Plugin:
        _MODEL_ID = "host"

    old = [{"inst_name": "a", "_id": 1}, {"inst_name": "gone", "_id": 2}]
    new = [{"inst_name": "a"}]
    m = _mgmt(
        monkeypatch,
        fake,
        old,
        new,
        collect_plugin=Plugin(),
        data_cleanup_strategy=DataCleanupStrategy.IMMEDIATELY,
    )
    assert [i["inst_name"] for i in m.delete_list] == ["gone"]


def test_contrast_immediately_skips_delete_when_no_model_id(monkeypatch):
    fake = FakeGraph()
    old = [{"inst_name": "gone", "_id": 2}]
    new = [{"inst_name": "a"}]
    # collect_plugin 无 _MODEL_ID → 不删除
    m = _mgmt(
        monkeypatch,
        fake,
        old,
        new,
        collect_plugin=object(),
        data_cleanup_strategy=DataCleanupStrategy.IMMEDIATELY,
    )
    assert m.delete_list == []


# --------------------------------------------------------------------------
# add_inst
# --------------------------------------------------------------------------
def test_add_inst_success_and_schedule(monkeypatch):
    fake = FakeGraph(query_entity=lambda _label, c: ([], 0), new_id=55)
    m = _mgmt(monkeypatch, fake, [], [])
    scheduled = []
    import apps.cmdb.services.auto_relation_reconcile as ar

    monkeypatch.setattr(ar, "schedule_instance_auto_relation_reconcile", lambda ids: scheduled.append(list(ids)))
    result = m.add_inst([{"inst_name": "new", "assos": []}])
    assert len(result["success"]) == 1
    assert result["success"][0]["inst_info"]["_id"] == 55
    assert scheduled == [[55]]
    assert len(fake.created_entities) == 1
    from uuid import UUID

    assert UUID(fake.created_entities[0]["inst_uuid"]).version == 4


def test_add_inst_failure_goes_to_failed(monkeypatch):
    fake = FakeGraph(query_entity=lambda _label, c: ([], 0), create_entity_raises=ValueError("dup"))
    m = _mgmt(monkeypatch, fake, [], [])
    result = m.add_inst([{"inst_name": "new", "assos": []}])
    assert result["success"] == []
    assert len(result["failed"]) == 1
    assert "dup" in str(result["failed"][0]["error"])


def test_add_inst_empty_noop(monkeypatch):
    fake = FakeGraph()
    m = _mgmt(monkeypatch, fake, [], [])
    assert m.add_inst([]) == {"success": [], "failed": []}


# --------------------------------------------------------------------------
# update_inst
# --------------------------------------------------------------------------
def test_update_inst_success(monkeypatch):
    fake = FakeGraph(query_entity=lambda _label, c: ([{"_id": 7, "inst_name": "a"}], 1))
    m = _mgmt(monkeypatch, fake, [], [])
    result = m.update_inst([{"_id": 7, "inst_name": "a", "assos": []}])
    assert len(result["success"]) == 1
    assert result["success"][0]["inst_info"]["inst_name"] == "a"


def test_update_inst_queries_only_unique_candidates(monkeypatch):
    fake = FakeGraph(query_entity=lambda _label, c: ([{"_id": 7, "inst_name": "a"}], 1))
    attrs = [{"attr_id": "inst_name", "attr_name": "名称", "is_only": True, "editable": True}]
    m = _mgmt(monkeypatch, fake, [], [], attrs=attrs)

    m.update_inst([{"_id": 7, "inst_name": "a", "assos": []}])

    assert fake.queries == [
        (
            "instance",
            [
                {"field": "model_id", "type": "str=", "value": "host"},
                {"field": "inst_name", "type": "str[]", "value": ["a"]},
            ],
        )
    ]


def test_refresh_heartbeat_updates_only_runtime_metadata_without_querying_instances(monkeypatch):
    fake = FakeGraph(query_entity=lambda _label, c: ([{"_id": 7, "inst_name": "a"}], 1))
    m = _mgmt(monkeypatch, fake, [], [])
    scheduled = []
    import apps.cmdb.services.auto_relation_reconcile as ar

    monkeypatch.setattr(ar, "schedule_instance_auto_relation_reconcile", lambda ids: scheduled.append(ids))
    result = m.refresh_heartbeat([{"_id": 7, "inst_name": "a"}])
    assert len(result["success"]) == 1
    assert fake.set_props == [
        {
            "_id": 7,
            "model_id": "host",
            "organization": [1],
            "collect_task": 1,
            "auto_collect": True,
            "collect_time": "2026-06-24",
        }
    ]
    assert fake.queries == []
    assert fake.set_exist_items == [[]]
    assert scheduled == []


@pytest.mark.parametrize("driver_name", ["falkordb", "neo4j"])
def test_refresh_heartbeat_rejects_conflicting_runtime_unique_candidate(monkeypatch, driver_name):
    from apps.cmdb.graph.falkordb import FalkorDBClient
    from apps.cmdb.graph.neo4j import Neo4jClient

    unique_checker = {
        "falkordb": FalkorDBClient.check_unique_attr,
        "neo4j": Neo4jClient.check_unique_attr,
    }[driver_name]

    def validate_with_real_unique_check(label, ids, info, check_attr_map, exist_items):
        unique_checker(
            info,
            check_attr_map["is_only"],
            exist_items,
            is_update=True,
        )
        return [dict(info)]

    fake = FakeGraph(
        query_entity=lambda _label, c: (
            [
                {"_id": 7, "collect_task": "task-1"},
                {"_id": 8, "collect_task": "task-1"},
            ],
            2,
        ),
        set_entity_properties=validate_with_real_unique_check,
    )
    attrs = [{"attr_id": "collect_task", "attr_name": "采集任务", "is_only": True, "editable": True}]
    m = _mgmt(monkeypatch, fake, [], [], attrs=attrs, task_id="task-1")

    result = m.refresh_heartbeat([{"_id": 7, "inst_name": "a"}])

    assert fake.queries == [
        (
            "instance",
            [
                {"field": "model_id", "type": "str=", "value": "host"},
                {"field": "collect_task", "type": "str[]", "value": ["task-1"]},
            ],
        )
    ]
    assert fake.set_exist_items == [[{"_id": 8, "collect_task": "task-1"}]]
    assert result["success"] == []
    assert len(result["failed"]) == 1
    assert "采集任务 exist" in str(result["failed"][0]["error"])


def test_refresh_heartbeat_isolates_each_write_failure(monkeypatch):
    def fail_first_write(label, ids, info, check_attr_map, exist_items):
        if ids == [7]:
            raise RuntimeError("write failed")
        return [dict(info)]

    fake = FakeGraph(set_entity_properties=fail_first_write)
    m = _mgmt(monkeypatch, fake, [], [])

    result = m.refresh_heartbeat([{"_id": 7}, {"_id": 8}])

    assert [item["inst_info"]["_id"] for item in result["success"]] == [8]
    assert [item["instance_info"]["_id"] for item in result["failed"]] == [7]
    assert "write failed" in str(result["failed"][0]["error"])


def test_refresh_heartbeat_keeps_candidate_query_failure_batch_scoped(monkeypatch):
    def fail_query(label, conditions):
        raise RuntimeError("query failed")

    fake = FakeGraph(query_entity=fail_query)
    attrs = [{"attr_id": "collect_task", "attr_name": "采集任务", "is_only": True, "editable": True}]
    m = _mgmt(monkeypatch, fake, [], [], attrs=attrs, task_id="task-1")

    with pytest.raises(RuntimeError, match="query failed"):
        m.refresh_heartbeat([{"_id": 7}])


def test_refresh_heartbeat_keeps_missing_id_as_batch_error(monkeypatch):
    fake = FakeGraph()
    m = _mgmt(monkeypatch, fake, [], [])

    with pytest.raises(KeyError, match="_id"):
        m.refresh_heartbeat([{"inst_name": "missing-id"}])


def test_controller_heartbeat_is_reported_but_excluded_from_audit(monkeypatch):
    fake = FakeGraph(query_entity=lambda _label, c: ([{"_id": 1, "inst_name": "a"}], 1))
    old = [{"inst_name": "a", "_id": 1}]
    new = [{"inst_name": "a"}]
    m = _mgmt(monkeypatch, fake, old, new)
    audited = []
    monkeypatch.setattr(
        mod,
        "write_collect_instance_change_records",
        lambda management, result: audited.append(result),
    )
    result = m.controller()
    assert len(result["update"]["success"]) == 1
    assert result["update"]["success"][0]["heartbeat"] is True
    assert audited[0]["update"]["success"] == []


# --------------------------------------------------------------------------
# delete_inst
# --------------------------------------------------------------------------
def test_delete_inst_success(monkeypatch):
    fake = FakeGraph()
    _patch_common(monkeypatch, fake)
    captured = []
    import apps.cmdb.services.auto_relation_reconcile as ar

    monkeypatch.setattr(ar, "schedule_incoming_rule_full_sync_by_model_ids", lambda ids: captured.append(list(ids)))
    result = Management.delete_inst([{"_id": 3, "model_id": "host"}])
    assert result["success"][0]["_id"] == 3
    assert fake.deleted == [3]
    assert captured == [["host"]]


def test_delete_inst_empty(monkeypatch):
    fake = FakeGraph()
    _patch_common(monkeypatch, fake)
    assert Management.delete_inst([]) == {"success": [], "failed": []}


# --------------------------------------------------------------------------
# set_asso_info / setting_assos
# --------------------------------------------------------------------------
def test_set_asso_info_builds_contract(monkeypatch):
    fake = FakeGraph()
    m = _mgmt(monkeypatch, fake, [], [])
    src = {"model_id": "vm", "_id": 1, "inst_name": "src"}
    dst = {"model_id": "host", "model_asst_id": "vm_run_host", "asst_id": "run"}
    info = m.set_asso_info(11, src, dst)
    assert info == {
        "model_asst_id": "vm_run_host",
        "src_model_id": "vm",
        "src_inst_id": 1,
        "dst_model_id": "host",
        "dst_inst_id": 11,
        "asst_id": "run",
    }


def test_setting_assos_success(monkeypatch):
    fake = FakeGraph(query_entity=lambda _label, c: ([{"_id": 11}], 1))
    m = _mgmt(monkeypatch, fake, [], [])
    src = {"model_id": "vm", "_id": 1, "inst_name": "src"}
    dst_list = [{"model_id": "host", "inst_name": "h1", "model_asst_id": "vm_run_host", "asst_id": "run"}]
    out = m.setting_assos(src, dst_list)
    assert len(out["success"]) == 1
    assert out["success"][0]["src_model_id"] == "vm"
    assert out["success"][0]["src_inst_id"] == 1
    assert out["success"][0]["dst_model_id"] == "host"
    assert out["success"][0]["dst_inst_id"] == 11
    assert len(fake.created_edges) == 1
    args, _kwargs = fake.created_edges[0]
    assert args[1] == 1
    assert args[3] == 11


def test_setting_assos_contains_orients_parent_src_to_child_dst(monkeypatch):
    """physcial_server_contains_nic：图边 src=父机 dst=nic，而不是 nic→父机。"""
    fake = FakeGraph(
        query_entity=lambda _label, c: (
            [{"_id": 1, "inst_name": "srv-1", "model_id": "physcial_server"}],
            1,
        )
    )
    m = _mgmt(monkeypatch, fake, [], [])
    current = {"model_id": "nic", "_id": 99, "inst_name": "aa:bb:cc:dd:ee:01"}
    listed = [
        {
            "model_id": "physcial_server",
            "inst_name": "srv-1",
            "asst_id": "contains",
            "model_asst_id": "physcial_server_contains_nic",
        }
    ]
    out = m.setting_assos(current, listed)
    assert len(out["success"]) == 1
    info = out["success"][0]
    assert info["model_asst_id"] == "physcial_server_contains_nic"
    assert info["src_model_id"] == "physcial_server"
    assert info["src_inst_id"] == 1
    assert info["src_inst_name"] == "srv-1"
    assert info["dst_model_id"] == "nic"
    assert info["dst_inst_id"] == 99
    assert info["dst_inst_name"] == "aa:bb:cc:dd:ee:01"
    args, _kwargs = fake.created_edges[0]
    # create_edge(label, a_id/src, a_label, b_id/dst, ...)
    assert args[1] == 1
    assert args[3] == 99
    # 旧实现把当前 nic 当 src、父机当 dst，下列断言必须失败
    assert args[1] != 99
    assert args[3] != 1


def test_setting_assos_target_not_found(monkeypatch):
    fake = FakeGraph(query_entity=lambda _label, c: ([], 0))
    m = _mgmt(monkeypatch, fake, [], [])
    src = {"model_id": "vm", "_id": 1, "inst_name": "src"}
    dst_list = [{"model_id": "host", "inst_name": "missing", "model_asst_id": "vm_run_host", "asst_id": "run"}]
    out = m.setting_assos(src, dst_list)
    assert out["success"] == []
    assert len(out["failed"]) == 1
    assert "not found" in out["failed"][0]["error"]


def test_setting_assos_edge_already_exists_is_idempotent_success(monkeypatch):
    fake = FakeGraph(
        query_entity=lambda _label, c: ([{"_id": 11}], 1),
        create_edge_raises=Exception("edge already exists"),
    )
    m = _mgmt(monkeypatch, fake, [], [])
    src = {"model_id": "vm", "_id": 1, "inst_name": "src"}
    dst_list = [{"model_id": "host", "inst_name": "h1", "model_asst_id": "vm_run_host", "asst_id": "run"}]
    out = m.setting_assos(src, dst_list)
    # "edge already exists" 视为幂等成功
    assert len(out["success"]) == 1
    assert out["failed"] == []


# --------------------------------------------------------------------------
# update / controller 编排
# --------------------------------------------------------------------------
def test_controller_runs_delete_add_update(monkeypatch):
    fake = FakeGraph(query_entity=lambda _label, c: ([], 0))
    old = [{"inst_name": "a", "_id": 1}]
    new = [{"inst_name": "a"}, {"inst_name": "b"}]
    m = _mgmt(monkeypatch, fake, old, new)
    result = m.controller()
    assert set(result.keys()) == {"add", "update", "delete"}
    # b 为新增
    assert len(result["add"]["success"]) == 1


def test_controller_queries_only_unique_candidates_for_business_changes(monkeypatch):
    fake = FakeGraph(query_entity=lambda _label, c: ([{"_id": 1, "inst_name": "a"}], 1))
    attrs = [{"attr_id": "inst_name", "attr_name": "名称", "is_only": True, "editable": True}]
    old = [{"inst_name": "a", "_id": 1}]
    new = [{"inst_name": "a"}, {"inst_name": "b"}]
    m = _mgmt(monkeypatch, fake, old, new, attrs=attrs)

    m.controller()

    assert fake.queries == [
        (
            "instance",
            [
                {"field": "model_id", "type": "str=", "value": "host"},
                {"field": "inst_name", "type": "str[]", "value": ["b"]},
            ],
        ),
    ]


def test_update_only_runs_update(monkeypatch):
    fake = FakeGraph(query_entity=lambda _label, c: ([{"_id": 1, "inst_name": "a"}], 1))
    old = [{"inst_name": "a", "_id": 1}]
    new = [{"inst_name": "a"}]
    m = _mgmt(monkeypatch, fake, old, new)
    result = m.update()
    assert result["add"] == {"success": [], "failed": []}
    assert result["delete"] == {"success": [], "failed": []}
    assert len(result["update"]["success"]) == 1


def test_manual_update_writes_nothing_when_old_data_empty(monkeypatch):
    """手动只更新：对账不到已有 CI 时不会新增。扫描生成的采集若没认领 collect_task 就会是这种 0/0。"""
    fake = FakeGraph(query_entity=lambda _label, c: ([], 0))
    m = _mgmt(monkeypatch, fake, [], [{"inst_name": "10.0.1.10-switch", "ip_addr": "10.0.1.10"}])
    result = m.update()
    assert result["add"] == {"success": [], "failed": []}
    assert result["update"] == {"success": [], "failed": []}
    assert m.add_list[0]["inst_name"] == "10.0.1.10-switch"
