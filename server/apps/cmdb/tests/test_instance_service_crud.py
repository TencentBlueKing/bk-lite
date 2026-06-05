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
