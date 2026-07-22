"""CMDB 模型属性 BDD（中文 Gherkin）。

对照 specs/capabilities/legacy-prd-cmdb-模型管理.md·属性：
- create / update / delete model_attr 流程；
- enum 字段 enum_rule_type / enum_select_mode 不可变约束；
- enum 属性默认值规范化；
- attr_id 重复、模型不存在、属性不存在的拒绝。

3 happy + 6 corner。
"""

import json
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.cmdb.services.model import ModelManage
from apps.core.exceptions.base_app_exception import BaseAppException

FEATURE = str(Path(__file__).parent / "model_attr.feature")
scenarios(FEATURE)

MODULE = "apps.cmdb.services.model"


@pytest.fixture
def ctx():
    return {"result": None, "error": None, "current_attr": {}, "incoming_attr": {}, "target_attr": {}}


@pytest.fixture(autouse=True)
def _patch_side_effects(monkeypatch):
    monkeypatch.setattr(f"{MODULE}.create_change_record", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change", lambda mid: None
    )
    monkeypatch.setattr(f"{MODULE}.guard_attr_change_against_unique_rules", lambda *a, **k: None)


@given("模型属性服务的旁路依赖已被打桩")
def _bg_ok():
    pass


# ---------------------------------------------------------------------------
# 假设
# ---------------------------------------------------------------------------

def _seed_with_attrs(fake_graph, model_id, model_name, attrs):
    """fake set_entity_properties 回显 payload 的 attrs，模拟图库返回最新 attrs。"""
    def _set_props(label, ids, data, *args, **kwargs):
        return [{"_id": ids[0], "attrs": data.get("attrs", "[]")}]

    fake_graph(
        MODULE,
        query_entity=([{"_id": 1, "model_id": model_id, "model_name": model_name, "attrs": json.dumps(attrs)}], 1),
        set_entity_properties=_set_props,
        remove_entitys_properties={},
    )


@given(parsers.parse('图库中存在模型 model_id="{model_id}" model_name="{model_name}" attrs="[]"'))
def _seed_empty_model(fake_graph, model_id, model_name):
    _seed_with_attrs(fake_graph, model_id, model_name, [])


@given(parsers.re(
    r'图库中存在模型 model_id="(?P<model_id>[^"]+)" model_name="(?P<model_name>[^"]+)" attrs=(?P<attrs>\[.*\])$'
))
def _seed_with_attrs_step(fake_graph, model_id, model_name, attrs):
    parsed = json.loads(attrs)
    _seed_with_attrs(fake_graph, model_id, model_name, parsed)


@given("图库中没有任何模型")
def _seed_no_model(fake_graph):
    fake_graph(MODULE, query_entity=([], 0))


@given(parsers.parse('当前属性 attr_type="{attr_type}" enum_rule_type="{rule}"'))
def _seed_current_rule(ctx, attr_type, rule):
    ctx["current_attr"] = {"attr_type": attr_type, "enum_rule_type": rule}


@given(parsers.parse('传入属性 attr_type="{attr_type}" enum_rule_type="{rule}"'))
def _seed_incoming_rule(ctx, attr_type, rule):
    ctx["incoming_attr"] = {"attr_type": attr_type, "enum_rule_type": rule}


@given(parsers.parse('当前属性 attr_type="{attr_type}" enum_select_mode="{mode}"'))
def _seed_current_mode(ctx, attr_type, mode):
    ctx["current_attr"] = {"attr_type": attr_type, "enum_select_mode": mode}


@given(parsers.parse('传入属性 attr_type="{attr_type}" enum_select_mode="{mode}"'))
def _seed_incoming_mode(ctx, attr_type, mode):
    ctx["incoming_attr"] = {"attr_type": attr_type, "enum_select_mode": mode}


@given(parsers.parse('待规范属性 attr_type="{attr_type}"'))
def _seed_target_attr(ctx, attr_type):
    ctx["target_attr"] = {"attr_type": attr_type}


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

def _attr_factory(raw: str) -> dict:
    a = json.loads(raw)
    a.setdefault("editable", True)
    a.setdefault("is_required", False)
    a.setdefault("is_only", False)
    a.setdefault("attr_group", "g")
    a.setdefault("option", {})
    a.setdefault("user_prompt", "")
    a.setdefault("default_value", [])
    return a


@when(parsers.re(r'用户 "(?P<operator>[^"]+)" 创建模型属性 model_id="(?P<model_id>[^"]+)" attr=(?P<attr>\{.*\})$'))
def _when_create_attr(ctx, operator, model_id, attr):
    try:
        ctx["result"] = ModelManage.create_model_attr(model_id, _attr_factory(attr), operator)
    except BaseAppException as exc:
        ctx["error"] = exc


@when(parsers.re(r'用户 "(?P<operator>[^"]+)" 尝试创建模型属性 model_id="(?P<model_id>[^"]+)" attr=(?P<attr>\{.*\})$'))
def _when_create_attr_corner(ctx, operator, model_id, attr):
    _when_create_attr(ctx, operator, model_id, attr)


@when(parsers.re(r'用户 "(?P<operator>[^"]+)" 更新模型属性 model_id="(?P<model_id>[^"]+)" attr=(?P<attr>\{.*\})$'))
def _when_update_attr(ctx, operator, model_id, attr):
    try:
        ctx["result"] = ModelManage.update_model_attr(model_id, _attr_factory(attr), operator)
    except BaseAppException as exc:
        ctx["error"] = exc


@when(parsers.re(r'用户 "(?P<operator>[^"]+)" 尝试更新模型属性 model_id="(?P<model_id>[^"]+)" attr=(?P<attr>\{.*\})$'))
def _when_update_attr_corner(ctx, operator, model_id, attr):
    _when_update_attr(ctx, operator, model_id, attr)


@when(parsers.parse('用户 "{operator}" 删除模型属性 model_id="{model_id}" attr_id="{attr_id}"'))
def _when_delete_attr(ctx, operator, model_id, attr_id):
    try:
        ModelManage.delete_model_attr(model_id, attr_id, operator)
        ctx["result"] = "ok"
    except BaseAppException as exc:
        ctx["error"] = exc


@when("我调用 validate_enum_rule_immutable")
def _when_rule_immutable(ctx):
    try:
        ModelManage.validate_enum_rule_immutable(ctx["current_attr"], ctx["incoming_attr"])
        ctx["result"] = "ok"
    except BaseAppException as exc:
        ctx["error"] = exc


@when("我调用 validate_enum_select_mode_immutable")
def _when_mode_immutable(ctx):
    try:
        ModelManage.validate_enum_select_mode_immutable(ctx["current_attr"], ctx["incoming_attr"])
        ctx["result"] = "ok"
    except BaseAppException as exc:
        ctx["error"] = exc


@when("我调用 ensure_enum_select_mode")
def _when_ensure_mode(ctx):
    ctx["result"] = ModelManage.ensure_enum_select_mode(ctx["target_attr"])


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

@then("属性创建应当成功")
@then("属性更新应当成功")
@then("属性删除应当成功")
def _no_error(ctx):
    assert ctx["error"] is None, f"unexpected error: {ctx['error']}"


@then(parsers.parse('新增属性的 attr_id 应当为 "{value}"'))
def _attr_id(ctx, value):
    assert ctx["result"]["attr_id"] == value


@then(parsers.parse('更新后的属性 attr_name 应当为 "{value}"'))
def _attr_name(ctx, value):
    assert ctx["result"]["attr_name"] == value


@then(parsers.parse('属性 enum_select_mode 应当为 "{value}"'))
def _enum_mode(ctx, value):
    assert ctx["result"]["enum_select_mode"] == value


@then(parsers.parse('应当抛出业务异常，消息包含 "{snippet}"'))
def _expect_error(ctx, snippet):
    assert ctx["error"] is not None, "expected BaseAppException, got none"
    assert snippet in str(ctx["error"]), ctx["error"]
