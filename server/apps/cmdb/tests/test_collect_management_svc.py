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

from apps.cmdb.collection import common as mod
from apps.cmdb.collection.common import Management
from apps.cmdb.constants.constants import DataCleanupStrategy


class FakeGraph:
    def __init__(self, **returns):
        self.returns = returns
        self.created_entities = []
        self.created_edges = []
        self.deleted = []
        self.set_props = []
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
        task_id=1,
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
def test_contrast_classifies_add_and_update(monkeypatch):
    fake = FakeGraph()
    old = [{"inst_name": "a", "_id": 1}]
    new = [{"inst_name": "a"}, {"inst_name": "b"}]
    m = _mgmt(monkeypatch, fake, old, new)
    assert [i["inst_name"] for i in m.add_list] == ["b"]
    assert [i["inst_name"] for i in m.update_list] == ["a"]
    # update 项注入了既有 _id
    assert m.update_list[0]["_id"] == 1
    # 默认策略不删除
    assert m.delete_list == []


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
        monkeypatch, fake, old, new,
        collect_plugin=object(),
        data_cleanup_strategy=DataCleanupStrategy.IMMEDIATELY,
    )
    assert m.delete_list == []


# --------------------------------------------------------------------------
# add_inst
# --------------------------------------------------------------------------
def test_add_inst_success_and_schedule(monkeypatch):
    fake = FakeGraph(query_entity=lambda l, c: ([], 0), new_id=55)
    m = _mgmt(monkeypatch, fake, [], [])
    scheduled = []
    import apps.cmdb.services.auto_relation_reconcile as ar
    monkeypatch.setattr(ar, "schedule_instance_auto_relation_reconcile", lambda ids: scheduled.append(list(ids)))
    result = m.add_inst([{"inst_name": "new", "assos": []}])
    assert len(result["success"]) == 1
    assert result["success"][0]["inst_info"]["_id"] == 55
    assert scheduled == [[55]]
    assert len(fake.created_entities) == 1


def test_add_inst_failure_goes_to_failed(monkeypatch):
    fake = FakeGraph(query_entity=lambda l, c: ([], 0), create_entity_raises=ValueError("dup"))
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
    fake = FakeGraph(query_entity=lambda l, c: ([{"_id": 7, "inst_name": "a"}], 1))
    m = _mgmt(monkeypatch, fake, [], [])
    result = m.update_inst([{"_id": 7, "inst_name": "a", "assos": []}])
    assert len(result["success"]) == 1
    assert result["success"][0]["inst_info"]["inst_name"] == "a"


def test_update_inst_queries_only_unique_candidates(monkeypatch):
    fake = FakeGraph(query_entity=lambda l, c: ([{"_id": 7, "inst_name": "a"}], 1))
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
    fake = FakeGraph(query_entity=lambda l, c: ([{"_id": 11}], 1))
    m = _mgmt(monkeypatch, fake, [], [])
    src = {"model_id": "vm", "_id": 1, "inst_name": "src"}
    dst_list = [{"model_id": "host", "inst_name": "h1", "model_asst_id": "vm_run_host", "asst_id": "run"}]
    out = m.setting_assos(src, dst_list)
    assert len(out["success"]) == 1
    assert out["success"][0]["dst_inst_id"] == 11
    assert len(fake.created_edges) == 1


def test_setting_assos_target_not_found(monkeypatch):
    fake = FakeGraph(query_entity=lambda l, c: ([], 0))
    m = _mgmt(monkeypatch, fake, [], [])
    src = {"model_id": "vm", "_id": 1, "inst_name": "src"}
    dst_list = [{"model_id": "host", "inst_name": "missing", "model_asst_id": "vm_run_host", "asst_id": "run"}]
    out = m.setting_assos(src, dst_list)
    assert out["success"] == []
    assert len(out["failed"]) == 1
    assert "not found" in out["failed"][0]["error"]


def test_setting_assos_edge_already_exists_is_idempotent_success(monkeypatch):
    fake = FakeGraph(
        query_entity=lambda l, c: ([{"_id": 11}], 1),
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
    fake = FakeGraph(query_entity=lambda l, c: ([], 0))
    old = [{"inst_name": "a", "_id": 1}]
    new = [{"inst_name": "a"}, {"inst_name": "b"}]
    m = _mgmt(monkeypatch, fake, old, new)
    result = m.controller()
    assert set(result.keys()) == {"add", "update", "delete"}
    # b 为新增
    assert len(result["add"]["success"]) == 1


def test_controller_add_and_update_query_unique_candidates(monkeypatch):
    fake = FakeGraph(query_entity=lambda l, c: ([{"_id": 1, "inst_name": "a"}], 1))
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
        (
            "instance",
            [
                {"field": "model_id", "type": "str=", "value": "host"},
                {"field": "inst_name", "type": "str[]", "value": ["a"]},
            ],
        ),
    ]


def test_update_only_runs_update(monkeypatch):
    fake = FakeGraph(query_entity=lambda l, c: ([{"_id": 1, "inst_name": "a"}], 1))
    old = [{"inst_name": "a", "_id": 1}]
    new = [{"inst_name": "a"}]
    m = _mgmt(monkeypatch, fake, old, new)
    result = m.update()
    assert result["add"] == {"success": [], "failed": []}
    assert result["delete"] == {"success": [], "failed": []}
    assert len(result["update"]["success"]) == 1
