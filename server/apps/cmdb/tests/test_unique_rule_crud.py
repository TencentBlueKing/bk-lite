"""CMDB UniqueRule 增删改 + 候选字段 + 重排序覆盖测试。

对照 specs/capabilities/legacy-prd-cmdb-模型管理.md：唯一规则的创建/修改/删除完整路径、候选字段选择性判定、
build_unique_rules_from_attr_rows 入口校验。
"""

import json
from contextlib import contextmanager

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
        "apps.cmdb.services.unique_rule.search_model_info",
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
        "apps.cmdb.services.unique_rule.search_model_info",
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
        "apps.cmdb.services.unique_rule.search_model_info",
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
        "apps.cmdb.services.unique_rule.search_model_info",
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
        "apps.cmdb.services.unique_rule.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    with pytest.raises(BaseAppException):
        delete_unique_rule("host", "r_absent", "admin")


@pytest.mark.django_db
def test_delete_unique_rule_ok(monkeypatch, patch_save):
    rules_json = json.dumps([{"rule_id": "r1", "order": 1, "field_ids": ["ip"]}])
    monkeypatch.setattr(
        "apps.cmdb.services.unique_rule.search_model_info",
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
        "apps.cmdb.services.unique_rule.search_model_info",
        lambda mid: _model_info_with(rules_json, _BASIC_ATTRS),
    )
    out = list_unique_rules("host")
    assert len(out) == 1
    assert out[0]["field_names"] == ["IP"]


@pytest.mark.django_db
def test_list_candidate_fields(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.unique_rule.search_model_info",
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
        "apps.cmdb.services.unique_rule.search_model_info",
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
        "apps.cmdb.services.unique_rule.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    from apps.cmdb.services.unique_rule import build_unique_rules_from_attr_rows

    rows = [{"attr_id": "ip", "unique_rule_order": "notnumber"}]
    with pytest.raises(BaseAppException):
        build_unique_rules_from_attr_rows("host", rows)


@pytest.mark.django_db
def test_build_unique_rules_from_attr_rows_zero_order(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.unique_rule.search_model_info",
        lambda mid: _model_info_with("[]", _BASIC_ATTRS),
    )
    from apps.cmdb.services.unique_rule import build_unique_rules_from_attr_rows

    rows = [{"attr_id": "ip", "unique_rule_order": 0}]
    with pytest.raises(BaseAppException):
        build_unique_rules_from_attr_rows("host", rows)


@pytest.mark.django_db
def test_build_unique_rules_from_attr_rows_too_many(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.unique_rule.search_model_info",
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
        "apps.cmdb.services.unique_rule.search_model_info",
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


# --------------------------------------------------------------------------
# 同一模型的规则锁：锁内重读，避免整表覆盖
# --------------------------------------------------------------------------


_LOCK_ATTRS = [
    {"attr_id": "serial_a", "attr_name": "序列A", "attr_type": "str", "is_required": True},
    {"attr_id": "serial_b", "attr_name": "序列B", "attr_type": "str", "is_required": True},
    {"attr_id": "serial_c", "attr_name": "序列C", "attr_type": "str", "is_required": True},
    {"attr_id": "serial_d", "attr_name": "序列D", "attr_type": "str", "is_required": True},
]


def _stored_rule(rule_id, order, field_ids):
    return {"rule_id": rule_id, "order": order, "field_ids": list(field_ids)}


def _copy_stored_rules(rules):
    return [_stored_rule(rule["rule_id"], rule["order"], rule["field_ids"]) for rule in rules]


class _UniqueRuleLockHarness:
    """替换 UniqueWriteLockService.hold：进入锁之后，存储里才出现并发已保存的规则。"""

    def __init__(self):
        self.rules = {}
        self.instances = {}
        self.held = set()
        self.calls = []
        self.inflight = None
        self.pending_visible = {}

    def set_rules(self, model_id, rules):
        self.rules[model_id] = _copy_stored_rules(rules)

    def publish_on_lock(self, model_id, rules):
        self.pending_visible[model_id] = _copy_stored_rules(rules)

    @contextmanager
    def hold(self, lock_keys, *, lease_seconds=None):
        keys = tuple(str(key) for key in (lock_keys or ()))
        if set(keys) & self.held:
            raise BaseAppException("相同唯一键正在写入，请稍后重试")
        self.calls.append(keys)
        if keys and self.inflight in self.pending_visible:
            self.rules[self.inflight] = _copy_stored_rules(self.pending_visible[self.inflight])
        yield "owner-token"


def _install_unique_rule_lock_harness(monkeypatch, harness):
    from apps.cmdb.services.unique_write_lock import UniqueWriteLockService

    def search_model_info(model_id):
        return {
            "_id": 1,
            "model_id": model_id,
            "attrs": json.dumps(_LOCK_ATTRS),
            "unique_rules": json.dumps(harness.rules.get(model_id, [])),
        }

    def save_unique_rules(model_id, rules):
        harness.rules[model_id] = [
            _stored_rule(rule.rule_id, rule.order, rule.field_ids) for rule in rules
        ]

    monkeypatch.setattr(f"{MODULE}.search_model_info", search_model_info)
    monkeypatch.setattr(f"{MODULE}._save_unique_rules", save_unique_rules)
    monkeypatch.setattr(
        f"{MODULE}._query_model_instances",
        lambda model_id: list(harness.instances.get(model_id, [])),
    )
    monkeypatch.setattr(UniqueWriteLockService, "hold", harness.hold)


def _assert_model_lock_taken(harness):
    assert harness.calls, "保存必须进入该模型的规则锁"
    assert harness.calls[-1], "规则锁必须带上按模型区分的锁键"


@pytest.mark.django_db
def test_create_unique_rule_keeps_rule_saved_inside_lock(monkeypatch):
    harness = _UniqueRuleLockHarness()
    harness.set_rules("host", [])
    harness.publish_on_lock("host", [_stored_rule("r_a", 1, ["serial_a"])])
    harness.inflight = "host"
    _install_unique_rule_lock_harness(monkeypatch, harness)

    create_unique_rule("host", UniqueRulePayload(field_ids=["serial_b"]), "admin")

    _assert_model_lock_taken(harness)
    stored = {tuple(rule["field_ids"]): rule["rule_id"] for rule in harness.rules["host"]}
    assert stored[("serial_a",)] == "r_a"
    assert ("serial_b",) in stored
    assert len(stored) == 2


@pytest.mark.django_db
def test_update_unique_rule_keeps_rule_saved_inside_lock(monkeypatch):
    harness = _UniqueRuleLockHarness()
    harness.set_rules("host", [_stored_rule("r_a", 1, ["serial_a"])])
    harness.publish_on_lock(
        "host",
        [
            _stored_rule("r_a", 1, ["serial_a"]),
            _stored_rule("r_b", 2, ["serial_b"]),
        ],
    )
    harness.inflight = "host"
    _install_unique_rule_lock_harness(monkeypatch, harness)

    update_unique_rule("host", "r_a", UniqueRulePayload(field_ids=["serial_c"]), "admin")

    _assert_model_lock_taken(harness)
    stored = {rule["rule_id"]: rule["field_ids"] for rule in harness.rules["host"]}
    assert stored == {"r_a": ["serial_c"], "r_b": ["serial_b"]}


@pytest.mark.django_db
def test_delete_unique_rule_keeps_rule_saved_inside_lock(monkeypatch):
    harness = _UniqueRuleLockHarness()
    harness.set_rules("host", [_stored_rule("r_a", 1, ["serial_a"])])
    harness.publish_on_lock(
        "host",
        [
            _stored_rule("r_a", 1, ["serial_a"]),
            _stored_rule("r_b", 2, ["serial_b"]),
        ],
    )
    harness.inflight = "host"
    _install_unique_rule_lock_harness(monkeypatch, harness)

    delete_unique_rule("host", "r_a", "admin")

    _assert_model_lock_taken(harness)
    assert harness.rules["host"] == [_stored_rule("r_b", 1, ["serial_b"])]


@pytest.mark.django_db
def test_unique_rule_save_rejects_when_model_lock_is_held(monkeypatch):
    harness = _UniqueRuleLockHarness()
    harness.set_rules("host", [_stored_rule("r_a", 1, ["serial_a"])])
    harness.inflight = "host"
    _install_unique_rule_lock_harness(monkeypatch, harness)

    create_unique_rule("host", UniqueRulePayload(field_ids=["serial_b"]), "admin")
    _assert_model_lock_taken(harness)
    harness.held.update(harness.calls[-1])
    snapshot = _copy_stored_rules(harness.rules["host"])

    with pytest.raises(BaseAppException, match="相同唯一键正在写入，请稍后重试"):
        create_unique_rule("host", UniqueRulePayload(field_ids=["serial_c"]), "admin")

    assert harness.rules["host"] == snapshot


@pytest.mark.django_db
def test_other_model_unique_rule_lock_does_not_block_save(monkeypatch):
    harness = _UniqueRuleLockHarness()
    harness.set_rules("host", [])
    harness.set_rules("switch", [])
    _install_unique_rule_lock_harness(monkeypatch, harness)

    harness.inflight = "switch"
    create_unique_rule("switch", UniqueRulePayload(field_ids=["serial_a"]), "admin")
    switch_keys = harness.calls[-1]
    harness.inflight = "host"
    create_unique_rule("host", UniqueRulePayload(field_ids=["serial_b"]), "admin")
    host_keys = harness.calls[-1]

    assert switch_keys and host_keys
    assert set(switch_keys).isdisjoint(host_keys)

    harness.held.update(switch_keys)
    harness.set_rules("host", [])
    harness.publish_on_lock("host", [_stored_rule("r_a", 1, ["serial_a"])])
    harness.inflight = "host"
    create_unique_rule("host", UniqueRulePayload(field_ids=["serial_b"]), "admin")

    stored = {tuple(rule["field_ids"]) for rule in harness.rules["host"]}
    assert stored == {("serial_a",), ("serial_b",)}


@pytest.mark.django_db
def test_unique_rule_limit_uses_rules_read_inside_lock(monkeypatch):
    harness = _UniqueRuleLockHarness()
    harness.set_rules("host", [])
    harness.publish_on_lock(
        "host",
        [
            _stored_rule("r1", 1, ["serial_a"]),
            _stored_rule("r2", 2, ["serial_b"]),
            _stored_rule("r3", 3, ["serial_c"]),
        ],
    )
    harness.inflight = "host"
    _install_unique_rule_lock_harness(monkeypatch, harness)

    with pytest.raises(BaseAppException, match="最多只能配置 3"):
        create_unique_rule("host", UniqueRulePayload(field_ids=["serial_d"]), "admin")

    assert [rule["rule_id"] for rule in harness.rules["host"]] == ["r1", "r2", "r3"]


@pytest.mark.django_db
def test_unique_rule_field_check_uses_rules_read_inside_lock(monkeypatch):
    harness = _UniqueRuleLockHarness()
    harness.set_rules("host", [])
    harness.publish_on_lock("host", [_stored_rule("r_b", 1, ["serial_b"])])
    harness.inflight = "host"
    _install_unique_rule_lock_harness(monkeypatch, harness)

    with pytest.raises(BaseAppException, match="已被其他唯一规则使用"):
        create_unique_rule("host", UniqueRulePayload(field_ids=["serial_b"]), "admin")

    assert harness.rules["host"] == [_stored_rule("r_b", 1, ["serial_b"])]


@pytest.mark.django_db
def test_unique_rule_instance_conflict_uses_rules_read_inside_lock(monkeypatch):
    harness = _UniqueRuleLockHarness()
    harness.set_rules("host", [])
    harness.instances["host"] = [
        {"_id": 1, "inst_name": "host-a", "serial_a": "same", "serial_b": "b1"},
        {"_id": 2, "inst_name": "host-b", "serial_a": "same", "serial_b": "b2"},
    ]
    harness.publish_on_lock("host", [_stored_rule("r_a", 1, ["serial_a"])])
    harness.inflight = "host"
    _install_unique_rule_lock_harness(monkeypatch, harness)

    with pytest.raises(BaseAppException, match="与现有实例冲突"):
        create_unique_rule("host", UniqueRulePayload(field_ids=["serial_b"]), "admin")

    assert harness.rules["host"] == [_stored_rule("r_a", 1, ["serial_a"])]
