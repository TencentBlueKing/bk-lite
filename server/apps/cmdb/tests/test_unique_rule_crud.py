"""CMDB UniqueRule 增删改 + 候选字段 + 重排序覆盖测试。

对照 spec/prd/CMDB·模型管理：唯一规则的创建/修改/删除完整路径、候选字段选择性判定、
build_unique_rules_from_attr_rows 入口校验。
"""

import json

import pytest

from apps.cmdb.services.unique_rule import (
    UniqueRulePayload,
    create_unique_rule,
    delete_unique_rule,
    list_unique_rule_candidate_fields,
    list_unique_rules,
    reorder_unique_rules,
    update_unique_rule,
    ModelUniqueRule,
)
from apps.core.exceptions.base_app_exception import BaseAppException

MODULE = "apps.cmdb.services.unique_rule"


def _model_info_with(rules_json: str, attrs: list):
    return {
        "_id": 1, "model_id": "host",
        "attrs": json.dumps(attrs),
        "unique_rules": rules_json,
    }


_BASIC_ATTRS = [
    {"attr_id": "ip", "attr_name": "IP", "attr_type": "str", "is_required": True},
    {"attr_id": "name", "attr_name": "名称", "attr_type": "str", "is_required": True},
]


@pytest.fixture
def patch_save(monkeypatch):
    """跳过 _save_unique_rules 的图库写入。"""
    monkeypatch.setattr(f"{MODULE}._save_unique_rules", lambda mid, rules: None)
    monkeypatch.setattr(f"{MODULE}._query_model_instances", lambda mid: [])


# --------------------------------------------------------------------------
# create_unique_rule
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_unique_rule_ok(monkeypatch, patch_save):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    out = create_unique_rule(
        "host", UniqueRulePayload(field_ids=["ip"]), "admin"
    )
    # list_unique_rules 重新读取 model_info → 仍是 "[]"，所以返回空列表
    assert out == []


@pytest.mark.django_db
def test_create_unique_rule_invalid(monkeypatch, patch_save):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    with pytest.raises(BaseAppException):
        create_unique_rule(
            "host", UniqueRulePayload(field_ids=["inst_name"]), "admin"  # 禁用字段
        )


# --------------------------------------------------------------------------
# update_unique_rule
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_update_unique_rule_not_found(monkeypatch, patch_save):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    with pytest.raises(BaseAppException):
        update_unique_rule(
            "host", "r_absent", UniqueRulePayload(field_ids=["ip"]), "admin"
        )


@pytest.mark.django_db
def test_update_unique_rule_ok(monkeypatch, patch_save):
    rules_json = json.dumps([{"rule_id": "r1", "order": 1, "field_ids": ["ip"]}])
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with(rules_json, _BASIC_ATTRS),
    )
    save_calls = []
    monkeypatch.setattr(MODULE + "._save_unique_rules",
                        lambda mid, rules: save_calls.append((mid, [list(r.field_ids) for r in rules])))
    update_unique_rule("host", "r1", UniqueRulePayload(field_ids=["name"]), "admin")
    assert save_calls and save_calls[0][1] == [["name"]]


# --------------------------------------------------------------------------
# delete_unique_rule
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_unique_rule_not_found(monkeypatch, patch_save):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    with pytest.raises(BaseAppException):
        delete_unique_rule("host", "r_absent", "admin")


@pytest.mark.django_db
def test_delete_unique_rule_ok(monkeypatch, patch_save):
    rules_json = json.dumps([{"rule_id": "r1", "order": 1, "field_ids": ["ip"]}])
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with(rules_json, _BASIC_ATTRS),
    )
    save_calls = []
    monkeypatch.setattr(MODULE + "._save_unique_rules",
                        lambda mid, rules: save_calls.append((mid, [list(r.field_ids) for r in rules])))
    delete_unique_rule("host", "r1", "admin")
    # 删除规则后 _save_unique_rules 应被调用并传入空列表
    assert save_calls and save_calls[0][1] == []


# --------------------------------------------------------------------------
# list_unique_rules / list_unique_rule_candidate_fields
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_unique_rules(monkeypatch):
    rules_json = json.dumps([{"rule_id": "r1", "order": 1, "field_ids": ["ip"]}])
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with(rules_json, _BASIC_ATTRS),
    )
    out = list_unique_rules("host")
    assert len(out) == 1
    assert out[0]["field_names"] == ["IP"]


@pytest.mark.django_db
def test_list_candidate_fields(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    out = list_unique_rule_candidate_fields("host")
    by_id = {m.attr_id: m for m in out}
    # 必填的 ip/name 可选；非必填且禁用字段不可选
    assert by_id["ip"].selectable is True
    assert by_id["name"].selectable is True


@pytest.mark.django_db
def test_list_candidate_fields_with_occupied(monkeypatch):
    rules_json = json.dumps([{"rule_id": "r1", "order": 1, "field_ids": ["ip"]}])
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with(rules_json, _BASIC_ATTRS),
    )
    out = list_unique_rule_candidate_fields("host")
    by_id = {m.attr_id: m for m in out}
    # ip 已被规则占用 → 不可选
    assert by_id["ip"].selectable is False
    assert "已被" in by_id["ip"].disabled_reason or "占用" in by_id["ip"].disabled_reason


# --------------------------------------------------------------------------
# reorder_unique_rules（纯函数）
# --------------------------------------------------------------------------


def test_reorder_unique_rules_reassigns_orders():
    rules = [
        ModelUniqueRule(rule_id="r1", order=5, field_ids=["a"]),
        ModelUniqueRule(rule_id="r2", order=3, field_ids=["b"]),
        ModelUniqueRule(rule_id="r3", order=7, field_ids=["c"]),
    ]
    out = reorder_unique_rules(rules)
    assert [r.order for r in out] == [1, 2, 3]


# --------------------------------------------------------------------------
# build_unique_rules_from_attr_rows
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_build_unique_rules_from_attr_rows_invalid_order(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    from apps.cmdb.services.unique_rule import build_unique_rules_from_attr_rows

    rows = [{"attr_id": "ip", "unique_rule_order": "notnumber"}]
    with pytest.raises(BaseAppException):
        build_unique_rules_from_attr_rows("host", rows)


@pytest.mark.django_db
def test_build_unique_rules_from_attr_rows_zero_order(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    from apps.cmdb.services.unique_rule import build_unique_rules_from_attr_rows

    rows = [{"attr_id": "ip", "unique_rule_order": 0}]
    with pytest.raises(BaseAppException):
        build_unique_rules_from_attr_rows("host", rows)


@pytest.mark.django_db
def test_build_unique_rules_from_attr_rows_too_many(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    from apps.cmdb.services.unique_rule import build_unique_rules_from_attr_rows

    rows = [
        {"attr_id": "a", "unique_rule_order": 1},
        {"attr_id": "b", "unique_rule_order": 2},
        {"attr_id": "c", "unique_rule_order": 3},
        {"attr_id": "d", "unique_rule_order": 4},
    ]
    with pytest.raises(BaseAppException):
        build_unique_rules_from_attr_rows("host", rows)


@pytest.mark.django_db
def test_build_unique_rules_from_attr_rows_ok(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    from apps.cmdb.services.unique_rule import build_unique_rules_from_attr_rows

    rows = [
        {"attr_id": "ip", "unique_rule_order": 1},
        {"attr_id": "name", "unique_rule_order": 1},  # 同 order 形成联合规则
    ]
    out = build_unique_rules_from_attr_rows("host", rows)
    assert len(out) == 1
    assert set(out[0].field_ids) == {"ip", "name"}
