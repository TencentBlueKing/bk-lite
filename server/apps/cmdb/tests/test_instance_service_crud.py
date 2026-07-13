"""CMDB InstanceManage 增删改与关联覆盖测试（fake_graph + 旁路 mock）。

对照 spec/prd/CMDB·资产：实例创建、单条/批量修改、批量删除、关联创建/删除/详情、
全文检索系列、check_asso_mapping。
"""

import pytest

from apps.cmdb.services.instance import InstanceManage
from apps.core.exceptions.base_app_exception import BaseAppException

MODULE = "apps.cmdb.services.instance"


@pytest.fixture
def patch_side_effects(monkeypatch):
    """统一 mock change_record / auto_relation / 唯一规则校验 / DisplayFieldHandler。"""
    monkeypatch.setattr(f"{MODULE}.create_change_record", lambda *a, **k: None)
    monkeypatch.setattr(f"{MODULE}.batch_create_change_record", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile",
        lambda ids: None,
    )
    monkeypatch.setattr(
        f"{MODULE}.InstanceManage._build_unique_rule_check_attr_map",
        lambda model_id, attrs, for_update=False: {"is_only": {}, "is_required": {}, "unique_rules": [], "attrs_by_id": {}},
    )
    monkeypatch.setattr(
        "apps.cmdb.display_field.DisplayFieldHandler.build_display_fields",
        lambda model_id, info, attrs: info,
    )
    # ModelManage 数据
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr",
        lambda model_id, language="en": [
            {"attr_id": "inst_name", "attr_name": "名称", "attr_type": "str", "is_required": True},
        ],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda model_id: {"model_id": model_id, "model_name": "主机", "attrs": "[]", "_id": 1},
    )
    # 权限校验放行
    monkeypatch.setattr(
        f"{MODULE}.InstanceManage.check_instances_permission", lambda *a, **k: None
    )


# --------------------------------------------------------------------------
# instance_create
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_instance_create(fake_graph, patch_side_effects):
    fake_graph(
        MODULE,
        query_entity=([], 0),
        create_entity={"_id": 9, "model_id": "host", "inst_name": "h1"},
    )
    out = InstanceManage.instance_create(
        "host", {"inst_name": "h1"}, "admin", allowed_org_ids=[1]
    )
    assert out["_id"] == 9
    assert out["inst_name"] == "h1"


@pytest.mark.django_db
def test_instance_create_can_defer_audit_and_auto_relation(fake_graph, patch_side_effects, monkeypatch):
    graph = fake_graph(
        MODULE,
        query_entity=([], 0),
        create_entity={"_id": 9, "model_id": "host", "inst_name": "h1"},
    )
    monkeypatch.setattr(f"{MODULE}.create_change_record", lambda *a, **k: pytest.fail("审计不得同步执行"))
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile",
        lambda ids: pytest.fail("自动关联不得同步执行"),
    )

    out = InstanceManage.instance_create(
        "host",
        {"inst_name": "h1"},
        "admin",
        allowed_org_ids=[1],
        operation_id="operation-1",
        record_change=False,
        schedule_post_actions=False,
    )

    create_call = next(call for call in graph.calls if call[0] == "create_entity")
    assert out["_id"] == 9
    assert create_call[1][1]["_cmdb_operation_id"] == "operation-1"


@pytest.mark.django_db
def test_instance_create_queries_only_unique_rule_candidates(fake_graph, patch_side_effects, monkeypatch):
    from apps.cmdb.services.unique_rule import ModelUniqueRule

    query_params = []

    def query_entity(label, params, **kwargs):
        query_params.append(params)
        return [], 0

    fake_graph(
        MODULE,
        query_entity=query_entity,
        create_entity={"_id": 9, "model_id": "host", "inst_name": "h1", "serial": "S-1", "region": "cn"},
    )
    monkeypatch.setattr(
        f"{MODULE}.InstanceManage._build_unique_rule_check_attr_map",
        lambda model_id, attrs, for_update=False: {
            "is_only": {},
            "is_required": {},
            "unique_rules": [ModelUniqueRule(rule_id="r1", order=1, field_ids=["serial", "region"])],
            "attrs_by_id": {"serial": {"attr_name": "序列号"}, "region": {"attr_name": "区域"}},
        },
    )

    InstanceManage.instance_create(
        "host", {"inst_name": "h1", "serial": "S-1", "region": "cn"}, "admin", allowed_org_ids=[1]
    )

    assert len(query_params) == 1
    assert query_params[0] == [
        {"field": "model_id", "type": "str=", "value": "host"},
        {"field": "serial", "type": "str=", "value": "S-1"},
        {"field": "region", "type": "str=", "value": "cn"},
    ]


# --------------------------------------------------------------------------
# instance_update
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_instance_update_not_found(fake_graph, patch_side_effects):
    fake_graph(MODULE, query_entity_by_id={})
    with pytest.raises(BaseAppException):
        InstanceManage.instance_update([], [], 99, {"inst_name": "x"}, "admin")


@pytest.mark.django_db
def test_instance_update_ok(fake_graph, patch_side_effects):
    def _query(label, params, **k):
        return ([], 0)

    fake_graph(
        MODULE,
        query_entity_by_id={"_id": 5, "model_id": "host", "inst_name": "h1", "organization": [1]},
        query_entity=_query,
        set_entity_properties=[{"_id": 5, "model_id": "host", "inst_name": "h2", "organization": [1]}],
    )
    out = InstanceManage.instance_update(
        [{"id": 1}], ["admin"], 5, {"inst_name": "h2"}, "admin"
    )
    assert out["inst_name"] == "h2"


@pytest.mark.django_db
def test_instance_update_can_defer_audit_and_auto_relation(fake_graph, patch_side_effects, monkeypatch):
    graph = fake_graph(
        MODULE,
        query_entity_by_id={"_id": 5, "model_id": "host", "inst_name": "h1", "organization": [1]},
        query_entity=([], 0),
        set_entity_properties=[{"_id": 5, "model_id": "host", "inst_name": "h2", "organization": [1]}],
    )
    monkeypatch.setattr(f"{MODULE}.create_change_record", lambda *a, **k: pytest.fail("审计不得同步执行"))
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile",
        lambda ids: pytest.fail("自动关联不得同步执行"),
    )

    out = InstanceManage.instance_update(
        [{"id": 1}],
        ["admin"],
        5,
        {"inst_name": "h2"},
        "admin",
        operation_id="operation-1",
        record_change=False,
        schedule_post_actions=False,
    )

    update_call = next(call for call in graph.calls if call[0] == "set_entity_properties")
    assert out["inst_name"] == "h2"
    assert update_call[1][2]["_cmdb_operation_id"] == "operation-1"


# --------------------------------------------------------------------------
# batch_instance_update
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_batch_instance_update_not_found(fake_graph, patch_side_effects):
    fake_graph(MODULE, query_entity_by_ids=[])
    with pytest.raises(BaseAppException):
        InstanceManage.batch_instance_update([], [], [1], {"x": 1}, "admin")


@pytest.mark.django_db
def test_batch_instance_update_ok(fake_graph, patch_side_effects):
    fake_graph(
        MODULE,
        query_entity_by_ids=[{"_id": 1, "model_id": "host", "inst_name": "h1", "organization": [1]}],
        query_entity=([], 0),
        set_entity_properties=[{"_id": 1, "model_id": "host", "inst_name": "h2", "organization": [1]}],
    )
    out = InstanceManage.batch_instance_update(
        [{"id": 1}], ["admin"], [1], {"inst_name": "h2"}, "admin"
    )
    assert out[0]["inst_name"] == "h2"


@pytest.mark.django_db
def test_batch_instance_update_runs_file_field_hooks(fake_graph, patch_side_effects):
    # 编辑实例（前端走 batch_update）必须像 create/update 一样规范化并提交附件/图片字段，
    # 否则字段值不落成元数据 JSON、文件不落账 → 列表/详情无法回显且文件被 GC。
    from apps.cmdb.extensions import registry
    from apps.cmdb.instance_ops.extensions import InstanceEnterpriseExtension

    calls = {"normalize": 0, "commit": []}

    class _Spy(InstanceEnterpriseExtension):
        def normalize_file_fields(self, model_id, instance_data, attrs, *, operator, old_instance=None):
            calls["normalize"] += 1
            return instance_data

        def commit_instance_files(self, model_id, inst_id, saved, attrs, *, operator):
            calls["commit"].append(inst_id)

    saved_ext = registry._registry.get("instance_ops")
    registry.register("instance_ops", _Spy())
    try:
        fake_graph(
            MODULE,
            query_entity_by_ids=[{"_id": 1, "model_id": "host", "inst_name": "h1", "organization": [1]}],
            query_entity=([], 0),
            set_entity_properties=[{"_id": 1, "model_id": "host", "inst_name": "h2", "organization": [1]}],
        )
        InstanceManage.batch_instance_update(
            [{"id": 1}], ["admin"], [1], {"inst_name": "h2"}, "admin"
        )
    finally:
        if saved_ext is not None:
            registry.register("instance_ops", saved_ext)
        else:
            registry._registry.pop("instance_ops", None)

    assert calls["normalize"] == 1, "batch_instance_update 应规范化附件/图片字段"
    assert calls["commit"] == [1], "batch_instance_update 应对每个更新实例提交文件落账"


# --------------------------------------------------------------------------
# instance_batch_delete
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_instance_batch_delete_ok(fake_graph, patch_side_effects):
    fg = fake_graph(
        MODULE,
        query_entity_by_ids=[{"_id": 1, "model_id": "host", "inst_name": "h1", "organization": [1]}],
    )
    InstanceManage.instance_batch_delete([{"id": 1}], ["admin"], [1], "admin")
    # 验证 batch_delete_entity 调用了
    assert any(c[0] == "batch_delete_entity" for c in fg.calls)


# --------------------------------------------------------------------------
# instance_association_create / delete / by_asso_id
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_instance_association_create(fake_graph, patch_side_effects, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.create_change_record_by_asso", lambda *a, **k: None)
    monkeypatch.setattr(f"{MODULE}.InstanceManage.check_asso_mapping", lambda data: None)
    # 关键：instance_association_by_asso_id 返回包含 src/dst 的字典
    monkeypatch.setattr(
        f"{MODULE}.InstanceManage.instance_association_by_asso_id",
        lambda aid: {
            "src": {"_id": 1, "model_id": "host", "inst_name": "h"},
            "dst": {"_id": 2, "model_id": "sw", "inst_name": "s"},
        },
    )
    fake_graph(MODULE, create_edge={"_id": 100, "model_asst_id": "a_b_c"})
    out = InstanceManage.instance_association_create(
        {"src_inst_id": 1, "dst_inst_id": 2, "asst_id": "conn",
         "src_model_id": "host", "dst_model_id": "switch", "model_asst_id": "host_conn_switch"},
        "admin",
    )
    assert out["_id"] == 100


@pytest.mark.django_db
def test_instance_association_delete(fake_graph, patch_side_effects, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.create_change_record_by_asso", lambda *a, **k: None)
    monkeypatch.setattr(
        f"{MODULE}.InstanceManage.instance_association_by_asso_id",
        lambda aid: {
            "src": {"_id": 1, "model_id": "host", "inst_name": "h"},
            "dst": {"_id": 2, "model_id": "sw", "inst_name": "s"},
        },
    )
    fg = fake_graph(MODULE)
    InstanceManage.instance_association_delete(100, "admin")
    assert any(c[0] == "delete_edge" for c in fg.calls)


@pytest.mark.django_db
def test_instance_association_create_unresolved_endpoint(fake_graph, patch_side_effects, monkeypatch):
    """回归：端点实体未完全解析（dst 为空、src 缺 model_id，如接口↔接口并行边时
    query_edge_by_id 偶发回空端点）时，创建关联不应因拼接变更记录文案 KeyError 而 500。"""
    monkeypatch.setattr(f"{MODULE}.create_change_record_by_asso", lambda *a, **k: None)
    monkeypatch.setattr(f"{MODULE}.InstanceManage.check_asso_mapping", lambda data: None)
    monkeypatch.setattr(
        f"{MODULE}.InstanceManage.instance_association_by_asso_id",
        lambda aid: {"src": {"_id": 1, "inst_name": "if-a"}, "dst": {}},
    )
    fake_graph(MODULE, create_edge={"_id": 101, "model_asst_id": "interface_connect_interface"})
    out = InstanceManage.instance_association_create(
        {"src_inst_id": 1, "dst_inst_id": 2, "asst_id": "connect",
         "src_model_id": "interface", "dst_model_id": "interface",
         "model_asst_id": "interface_connect_interface"},
        "admin",
    )
    assert out["_id"] == 101


@pytest.mark.django_db
def test_instance_association_delete_unresolved_endpoint(fake_graph, patch_side_effects, monkeypatch):
    """回归：删除关联时端点实体未完全解析也不应 KeyError。"""
    monkeypatch.setattr(f"{MODULE}.create_change_record_by_asso", lambda *a, **k: None)
    monkeypatch.setattr(
        f"{MODULE}.InstanceManage.instance_association_by_asso_id",
        lambda aid: {"src": {"_id": 1, "inst_name": "if-a"}, "dst": {}},
    )
    fg = fake_graph(MODULE)
    InstanceManage.instance_association_delete(101, "admin")
    assert any(c[0] == "delete_edge" for c in fg.calls)


@pytest.mark.django_db
def test_instance_association_create_duplicate_raises_friendly(fake_graph, patch_side_effects, monkeypatch):
    """create_edge 报「edge already exists」时转成可读的 repetition 提示。"""
    monkeypatch.setattr(f"{MODULE}.InstanceManage.check_asso_mapping", lambda data: None)

    def dup(*a, **k):
        raise BaseAppException("edge already exists")

    fake_graph(MODULE, create_edge=dup)
    with pytest.raises(BaseAppException) as ei:
        InstanceManage.instance_association_create(
            {"src_inst_id": 1, "dst_inst_id": 2, "asst_id": "connect",
             "src_model_id": "interface", "dst_model_id": "interface",
             "model_asst_id": "interface_connect_interface"},
            "admin",
        )
    assert "repetition" in str(ei.value.message)


@pytest.mark.django_db
def test_instance_association_create_propagates_graph_error(fake_graph, patch_side_effects, monkeypatch):
    """回归：create_edge 抛非「edge already exists」异常时必须原样抛出，
    而不是被吞掉导致后续 edge 未赋值 UnboundLocalError 掩盖真实错误。"""
    monkeypatch.setattr(f"{MODULE}.InstanceManage.check_asso_mapping", lambda data: None)

    def boom(*a, **k):
        raise BaseAppException("graph down")

    fake_graph(MODULE, create_edge=boom)
    with pytest.raises(BaseAppException) as ei:
        InstanceManage.instance_association_create(
            {"src_inst_id": 1, "dst_inst_id": 2, "asst_id": "connect",
             "src_model_id": "interface", "dst_model_id": "interface",
             "model_asst_id": "interface_connect_interface"},
            "admin",
        )
    assert "graph down" in str(ei.value.message)


@pytest.mark.django_db
def test_instance_association_by_asso_id_found(fake_graph):
    fake_graph(MODULE, query_edge_by_id={"src": {"_id": 1}, "dst": {"_id": 2}, "_id": 100})
    out = InstanceManage.instance_association_by_asso_id(100)
    assert out["_id"] == 100


@pytest.mark.django_db
def test_instance_association_by_asso_id_missing(fake_graph):
    fake_graph(MODULE, query_edge_by_id={})
    assert InstanceManage.instance_association_by_asso_id(100) == {}


# --------------------------------------------------------------------------
# fulltext_search / fulltext_search_stats / fulltext_search_by_model
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_fulltext_search(fake_graph, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.InstanceManage._build_permission_params", classmethod(lambda cls, pmap, creator="": ("", {})))
    fake_graph(MODULE, full_text=[{"_id": 1, "inst_name": "h1", "model_id": "host"}])
    out = InstanceManage.fulltext_search(search="h", permission_map={1: {"inst_names": []}})
    assert len(out) == 1


@pytest.mark.django_db
def test_fulltext_search_stats(fake_graph, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.InstanceManage._build_permission_params", classmethod(lambda cls, pmap, creator="": ("", {})))
    fake_graph(MODULE, full_text_stats={"total": 3, "model_stats": [{"model_id": "host", "count": 3}]})
    out = InstanceManage.fulltext_search_stats(search="h", permission_map={1: {"inst_names": []}})
    assert out["total"] == 3


@pytest.mark.django_db
def test_fulltext_search_by_model(fake_graph, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.InstanceManage._build_permission_params", classmethod(lambda cls, pmap, creator="": ("", {})))
    fake_graph(MODULE, full_text_by_model={"total": 1, "data": [{"_id": 1}], "page": 1, "page_size": 10})
    out = InstanceManage.fulltext_search_by_model(
        search="h", model_id="host", permission_map={1: {"inst_names": []}}
    )
    assert out["total"] == 1


# --------------------------------------------------------------------------
# query_entity_by_id / query_entity_by_ids（直接 wrapper）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_query_entity_by_id_wrapper(fake_graph):
    fake_graph(MODULE, query_entity_by_id={"_id": 5, "inst_name": "h"})
    assert InstanceManage.query_entity_by_id(5)["_id"] == 5


@pytest.mark.django_db
def test_query_entity_by_ids_wrapper(fake_graph):
    fake_graph(MODULE, query_entity_by_ids=[{"_id": 1}, {"_id": 2}])
    assert len(InstanceManage.query_entity_by_ids([1, 2])) == 2


# --------------------------------------------------------------------------
# check_asso_mapping
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_check_asso_mapping_invalid(fake_graph):
    """缺少关键字段 → 抛异常"""
    with pytest.raises((BaseAppException, KeyError)):
        InstanceManage.check_asso_mapping({})


# --------------------------------------------------------------------------
# create_or_update / get_info（ShowField DB）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_or_update_empty():
    with pytest.raises(BaseAppException):
        InstanceManage.create_or_update({"show_fields": [], "model_id": "host", "created_by": "a"})


@pytest.mark.django_db
def test_create_or_update_ok():
    out = InstanceManage.create_or_update(
        {"show_fields": ["inst_name"], "model_id": "host", "created_by": "a"}
    )
    assert out["model_id"] == "host"


@pytest.mark.django_db
def test_get_info_none():
    assert InstanceManage.get_info("absent_model", "absent_user") is None


@pytest.mark.django_db
def test_get_info_found():
    InstanceManage.create_or_update(
        {"show_fields": ["inst_name"], "model_id": "host", "created_by": "u1"}
    )
    out = InstanceManage.get_info("host", "u1")
    assert out["model_id"] == "host"
