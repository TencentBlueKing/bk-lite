"""CMDB ModelManage 高阶方法覆盖：copy_model / auto_relation_rule 增删改 / unique_rule 入口。

对照 specs/capabilities/legacy-prd-cmdb-模型管理.md：模型复制（属性+关系）、自动关联规则增删改、模型唯一规则入口。
"""

import json

import pytest

from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.services.model import ModelManage
from apps.core.exceptions.base_app_exception import BaseAppException

MODULE = "apps.cmdb.services.model"


@pytest.fixture
def patch_side_effects(monkeypatch):
    monkeypatch.setattr(f"{MODULE}.create_change_record", lambda **k: None)
    monkeypatch.setattr(
        "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change", lambda model_id: None
    )
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_rule_auto_relation_full_sync",
        lambda ids: None,
    )


# --------------------------------------------------------------------------
# copy_model
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_copy_model_invalid_id():
    with pytest.raises(BaseAppException):
        ModelManage.copy_model("host", "1bad!", "新主机")


@pytest.mark.django_db
def test_copy_model_no_strategy():
    with pytest.raises(BaseAppException):
        ModelManage.copy_model("host", "host2", "新主机",
                               copy_attributes=False, copy_relationships=False)


@pytest.mark.django_db
def test_copy_model_src_missing(monkeypatch):
    monkeypatch.setattr(f"{MODULE}.ModelManage.search_model_info", lambda mid: {})
    with pytest.raises(BaseAppException):
        ModelManage.copy_model("absent", "host2", "新主机", copy_attributes=True)


@pytest.mark.django_db
def test_copy_model_ok_no_attributes(fake_graph, patch_side_effects, monkeypatch):
    monkeypatch.setattr(
        f"{MODULE}.ModelManage.search_model_info",
        lambda mid: {"model_id": mid, "model_name": "主机", "classification_id": "net",
                     "group": [1], "icn": "icon", "attrs": "[]", "_id": 1},
    )
    monkeypatch.setattr(
        f"{MODULE}.ClassificationManage.search_model_classification_info",
        lambda cid: {"_id": 50},
    )

    def _create_entity(label, data, check, exist):
        return {"_id": 7, "model_id": data["model_id"], "model_name": data["model_name"],
                "classification_id": data["classification_id"]}

    fake_graph(MODULE, query_entity=([], 0), query_edge=[], create_entity=_create_entity, create_edge={"_id": 1})
    out = ModelManage.copy_model(
        "host", "host2", "新主机", copy_attributes=False, copy_relationships=True,
    )
    assert out["model_id"] == "host2"
    # default 分组建好
    assert FieldGroup.objects.filter(model_id="host2", group_name="default").exists()


# --------------------------------------------------------------------------
# save_model_auto_relation_rule
# --------------------------------------------------------------------------


_STR_ATTRS = [{"attr_id": "ip", "attr_type": "str"}, {"attr_id": "name", "attr_type": "str"}]


@pytest.mark.django_db
def test_save_auto_relation_rule_no_assoc(monkeypatch):
    monkeypatch.setattr(f"{MODULE}.ModelManage.model_association_info_search", lambda mid: {})
    with pytest.raises(BaseAppException):
        ModelManage.save_model_auto_relation_rule("host", "a_b_c", {"match_pairs": []})


@pytest.mark.django_db
def test_save_auto_relation_rule_wrong_model(monkeypatch):
    monkeypatch.setattr(
        f"{MODULE}.ModelManage.model_association_info_search",
        lambda mid: {"src_model_id": "a", "dst_model_id": "b", "_id": 1},
    )
    with pytest.raises(BaseAppException):
        ModelManage.save_model_auto_relation_rule("nope", "a_b_c", {"match_pairs": []})


@pytest.mark.django_db
def test_save_auto_relation_rule_ok(fake_graph, patch_side_effects, monkeypatch):
    monkeypatch.setattr(
        f"{MODULE}.ModelManage.model_association_info_search",
        lambda mid: {"src_model_id": "host", "dst_model_id": "sw", "_id": 1},
    )
    monkeypatch.setattr(
        f"{MODULE}.ModelManage._get_model_attrs_for_auto_rule",
        lambda mid: _STR_ATTRS,
    )
    fake_graph(MODULE)
    payload = {
        "rule_id": "r1",
        "match_pairs": [{"src_field_id": "ip", "dst_field_id": "ip", "matching_rule": "exact"}],
    }
    out = ModelManage.save_model_auto_relation_rule("host", "host_conn_sw", payload, username="admin")
    assert out["rule_id"] == "r1"


# --------------------------------------------------------------------------
# update_model_auto_relation_rule
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_update_auto_relation_rule_no_existing(monkeypatch):
    monkeypatch.setattr(
        f"{MODULE}.ModelManage.model_association_info_search",
        lambda mid: {"src_model_id": "host", "dst_model_id": "sw", "_id": 1},
    )
    monkeypatch.setattr(
        f"{MODULE}.ModelManage._get_model_attrs_for_auto_rule", lambda mid: _STR_ATTRS
    )
    payload = {"match_pairs": [{"src_field_id": "ip", "dst_field_id": "ip", "matching_rule": "exact"}]}
    with pytest.raises(BaseAppException):
        ModelManage.update_model_auto_relation_rule("host", "host_conn_sw", "r1", payload)


@pytest.mark.django_db
def test_update_auto_relation_rule_rule_id_missing(monkeypatch):
    # 已存在另一条规则，但 rule_id 不匹配 → 抛"规则不存在"
    existing_rules = json.dumps({
        "version": 2,
        "rules": [{"rule_id": "other", "enabled": True,
                   "match_pairs": [{"src_field_id": "ip", "dst_field_id": "ip", "matching_rule": "exact"}]}],
    })
    monkeypatch.setattr(
        f"{MODULE}.ModelManage.model_association_info_search",
        lambda mid: {"src_model_id": "host", "dst_model_id": "sw", "_id": 1,
                     "auto_relation_rule": existing_rules},
    )
    monkeypatch.setattr(
        f"{MODULE}.ModelManage._get_model_attrs_for_auto_rule", lambda mid: _STR_ATTRS
    )
    payload = {"match_pairs": [{"src_field_id": "ip", "dst_field_id": "ip", "matching_rule": "exact"}]}
    with pytest.raises(BaseAppException):
        ModelManage.update_model_auto_relation_rule("host", "host_conn_sw", "r_absent", payload)


@pytest.mark.django_db
def test_update_auto_relation_rule_ok(fake_graph, patch_side_effects, monkeypatch):
    existing_rules = json.dumps({
        "version": 2,
        "rules": [{"rule_id": "r1", "enabled": True,
                   "match_pairs": [{"src_field_id": "ip", "dst_field_id": "ip", "matching_rule": "exact"}]}],
    })
    monkeypatch.setattr(
        f"{MODULE}.ModelManage.model_association_info_search",
        lambda mid: {"src_model_id": "host", "dst_model_id": "sw", "_id": 1,
                     "auto_relation_rule": existing_rules},
    )
    monkeypatch.setattr(
        f"{MODULE}.ModelManage._get_model_attrs_for_auto_rule", lambda mid: _STR_ATTRS
    )
    fake_graph(MODULE)
    payload = {"match_pairs": [{"src_field_id": "name", "dst_field_id": "name", "matching_rule": "exact"}]}
    out = ModelManage.update_model_auto_relation_rule("host", "host_conn_sw", "r1", payload)
    assert out["rule_id"] == "r1"


# --------------------------------------------------------------------------
# delete_model_auto_relation_rule
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_auto_relation_rule_no_existing(monkeypatch):
    monkeypatch.setattr(
        f"{MODULE}.ModelManage.model_association_info_search",
        lambda mid: {"src_model_id": "host", "dst_model_id": "sw", "_id": 1},
    )
    with pytest.raises(BaseAppException):
        ModelManage.delete_model_auto_relation_rule("host", "host_conn_sw", "r1")


@pytest.mark.django_db
def test_delete_auto_relation_rule_ok(fake_graph, patch_side_effects, monkeypatch):
    existing_rules = json.dumps({
        "version": 2,
        "rules": [{"rule_id": "r1", "enabled": True,
                   "match_pairs": [{"src_field_id": "ip", "dst_field_id": "ip", "matching_rule": "exact"}]}],
    })
    monkeypatch.setattr(
        f"{MODULE}.ModelManage.model_association_info_search",
        lambda mid: {"src_model_id": "host", "dst_model_id": "sw", "_id": 1,
                     "auto_relation_rule": existing_rules},
    )
    fg = fake_graph(MODULE)
    ModelManage.delete_model_auto_relation_rule("host", "host_conn_sw", "r1")
    # 删除规则会写回剩余规则（空规则集）→ set_edge_properties
    assert any(c[0] == "set_edge_properties" for c in fg.calls)


# --------------------------------------------------------------------------
# search_model_attr / search_model_info / search_model（已部分覆盖，补未覆盖分支）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_search_model_attr_v2(fake_graph):
    fake_graph(
        MODULE,
        query_entity=([{"_id": 1, "attrs": json.dumps([
            {"attr_id": "name", "attr_type": "str", "attr_name": "名称", "is_required": True},
        ])}], 1),
    )
    out = ModelManage.search_model_attr_v2("host")
    assert out[0]["attr_id"] == "name"


@pytest.mark.django_db
def test_search_model_attr_v2_caches_user_and_organization_options(fake_graph, monkeypatch):
    attrs = [
        {"attr_id": "owner", "attr_type": "user", "attr_name": "负责人"},
        {"attr_id": "org", "attr_type": "organization", "attr_name": "组织"},
    ]
    fake_graph(MODULE, query_entity=([{"_id": 1, "attrs": json.dumps(attrs)}], 1))
    monkeypatch.setattr(f"{MODULE}.cache.get", lambda key: None)

    cached = {}

    def fake_set(key, value, timeout=None):
        cached[key] = value

    monkeypatch.setattr(f"{MODULE}.cache.set", fake_set)
    monkeypatch.setattr(f"{MODULE}.SystemMgmt", lambda: object())

    calls = {"groups": 0, "users": 0}

    def fake_get_all_groups(client):
        calls["groups"] += 1
        return [{"id": "root", "name": "Root", "subGroups": []}]

    def fake_get_all_users(client):
        calls["users"] += 1
        return {"users": [{"id": 1, "username": "admin", "display_name": "Admin"}]}

    monkeypatch.setattr(f"{MODULE}.UserGroup.get_all_groups", fake_get_all_groups)
    monkeypatch.setattr(f"{MODULE}.UserGroup.get_all_users", fake_get_all_users)

    first = ModelManage.search_model_attr_v2("host")
    monkeypatch.setattr(f"{MODULE}.cache.get", lambda key: cached.get(key))
    second = ModelManage.search_model_attr_v2("host")

    assert calls == {"groups": 1, "users": 1}
    assert first[0]["option"] == second[0]["option"]
    assert first[1]["option"] == second[1]["option"]


@pytest.mark.django_db
def test_get_model_attrs_for_auto_rule_model_missing(monkeypatch):
    monkeypatch.setattr(f"{MODULE}.ModelManage.search_model_info", lambda mid: {})
    with pytest.raises(BaseAppException):
        ModelManage._get_model_attrs_for_auto_rule("absent")


@pytest.mark.django_db
def test_get_model_attrs_for_auto_rule_ok(monkeypatch):
    monkeypatch.setattr(
        f"{MODULE}.ModelManage.search_model_info",
        lambda mid: {"model_id": mid, "attrs": json.dumps([{"attr_id": "ip", "attr_type": "str"}])},
    )
    out = ModelManage._get_model_attrs_for_auto_rule("host")
    assert out[0]["attr_id"] == "ip"
