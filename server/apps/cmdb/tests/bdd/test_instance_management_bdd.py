"""CMDB 实例管理 BDD（中文 Gherkin）。

对照 spec/prd/CMDB·资产·实例：
- 模型属性 → 实例创建/更新校验属性映射；
- 导入结果聚合消息生成；
- 拓扑节点权限裁剪（按 inst 可见集合 + 中心节点保留策略）；
- 拓扑视图权限：实例为 None / 创建者命中 / 组织映射。

3 happy + 5 corner，全部走 InstanceManage 纯函数，不触图库。
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from apps.cmdb.services.instance import InstanceManage as IM

FEATURE = str(Path(__file__).parent / "instance_management.feature")
scenarios(FEATURE)


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

@pytest.fixture
def ctx():
    return {
        "attrs": [],
        "check_attr_map": None,
        "result": None,
        "topology": None,
        "visible_ids": set(),
        "pruned": None,
        "instance": None,
        "permission_map": None,
        "user": None,
    }


# ---------------------------------------------------------------------------
# 假设
# ---------------------------------------------------------------------------

@given(parsers.parse("模型属性集合为 {raw}"))
def _seed_attrs(ctx, raw):
    ctx["attrs"] = json.loads(raw)


@given(parsers.parse('一个全成功的导入结果 add={add:d} update={update:d} asso={asso:d}'))
def _seed_all_success(ctx, add, update, asso):
    ctx["result"] = {
        "add": {"success": add, "error": 0, "data": []},
        "update": {"success": update, "error": 0, "data": []},
        "asso": {"success": asso, "error": 0, "data": []},
    }


@given(parsers.re(
    r'一个导入结果 add=(?P<a>\d+) add_error=(?P<ae>\d+) add_data=(?P<ad>\[[^\]]*\]) '
    r'update=(?P<u>\d+) update_error=(?P<ue>\d+) asso=(?P<s>\d+) asso_error=(?P<se>\d+)'
))
def _seed_partial(ctx, a, ae, ad, u, ue, s, se):
    ctx["result"] = {
        "add": {"success": int(a), "error": int(ae), "data": json.loads(ad)},
        "update": {"success": int(u), "error": int(ue), "data": []},
        "asso": {"success": int(s), "error": int(se), "data": []},
    }


@given(parsers.re(r'一棵以 _id=(?P<root>\d+) 为根、子节点为 \[(?P<kids>[^\]]*)\] 的拓扑'))
def _seed_tree(ctx, root, kids):
    child_ids = [int(c.strip()) for c in kids.split(",") if c.strip()]
    ctx["topology"] = {
        "_id": int(root),
        "children": [{"_id": cid, "children": []} for cid in child_ids],
    }


@given(parsers.parse('一棵以 _id={root:d} 为根、无子节点的拓扑'))
def _seed_tree_empty(ctx, root):
    ctx["topology"] = {"_id": root, "children": []}


@given(parsers.re(r'可见节点集合为 \[(?P<ids>[^\]]*)\]'))
def _seed_visible(ctx, ids):
    ctx["visible_ids"] = {int(x.strip()) for x in ids.split(",") if x.strip()}


@given("可见节点集合为空")
def _seed_visible_empty(ctx):
    ctx["visible_ids"] = set()


@given(parsers.re(r'实例 _creator="(?P<creator>[^"]+)" organization=\[(?P<org>[^\]]*)\] model_id="(?P<model_id>[^"]+)"'))
def _seed_instance(ctx, creator, org, model_id):
    org_ids = [int(x.strip()) for x in org.split(",") if x.strip()]
    ctx["instance"] = {"_creator": creator, "organization": org_ids, "model_id": model_id}


@given(parsers.parse("权限映射 {raw}"))
def _seed_pmap(ctx, raw):
    # raw 形如 {4: {"permission_instances_map": {}}}
    ctx["permission_map"] = eval(raw, {"__builtins__": {}}, {})  # noqa: S307 — 测试场景且来源固定


@given(parsers.parse('当前用户 username="{username}"'))
def _seed_user(ctx, username):
    ctx["user"] = SimpleNamespace(username=username)


# ---------------------------------------------------------------------------
# 当
# ---------------------------------------------------------------------------

@when("我以非更新场景构造 check_attr_map")
def _build_check_attr_map_create(ctx):
    ctx["check_attr_map"] = IM._build_check_attr_map(ctx["attrs"], for_update=False)


@when("我以更新场景构造 check_attr_map")
def _build_check_attr_map_update(ctx):
    ctx["check_attr_map"] = IM._build_check_attr_map(ctx["attrs"], for_update=True)


@when("我调用 format_result_message")
def _call_format_result(ctx):
    ctx["status_msg"] = IM.format_result_message(ctx["result"])


@when(parsers.parse("我以中心节点 {center:d} 裁剪拓扑"))
def _prune(ctx, center):
    ctx["pruned"] = IM._prune_topology_node(ctx["topology"], ctx["visible_ids"], center)


@when("我对 None 实例调用 _has_topology_view_permission")
def _topo_perm_none(ctx):
    ctx["topo_perm"] = IM._has_topology_view_permission(None, {})


@when("我调用 _has_topology_view_permission")
def _topo_perm(ctx):
    ctx["topo_perm"] = IM._has_topology_view_permission(
        ctx["instance"], ctx["permission_map"], user=ctx["user"]
    )


# ---------------------------------------------------------------------------
# 那么
# ---------------------------------------------------------------------------

@then(parsers.re(r'is_only 映射的键集合应当为 \[(?P<keys>[^\]]*)\]'))
def _is_only_keys(ctx, keys):
    expected = {k.strip().strip('"') for k in keys.split(",") if k.strip()}
    assert set(ctx["check_attr_map"]["is_only"].keys()) == expected


@then(parsers.re(r'is_required 映射的键集合应当为 \[(?P<keys>[^\]]*)\]'))
def _is_required_keys(ctx, keys):
    expected = {k.strip().strip('"') for k in keys.split(",") if k.strip()}
    assert set(ctx["check_attr_map"]["is_required"].keys()) == expected


@then(parsers.parse('check_attr_map 中不应包含 "{key}" 键'))
def _no_key(ctx, key):
    assert key not in ctx["check_attr_map"]


@then(parsers.re(r'editable 映射的键集合应当为 \[(?P<keys>[^\]]*)\]'))
def _editable_keys(ctx, keys):
    expected = {k.strip().strip('"') for k in keys.split(",") if k.strip()}
    assert set(ctx["check_attr_map"]["editable"].keys()) == expected


@then(parsers.parse("整体状态应当为 {flag}"))
def _status_flag(ctx, flag):
    status, _ = ctx["status_msg"]
    assert status is (flag.lower() == "true")


@then("摘要消息应当为空")
def _msg_empty(ctx):
    _, msg = ctx["status_msg"]
    assert msg == ""


@then(parsers.parse('摘要消息应当包含 "{snippet}"'))
def _msg_contains(ctx, snippet):
    _, msg = ctx["status_msg"]
    assert snippet in msg, msg


@then(parsers.re(r'裁剪后的子节点 ids 应当为 \[(?P<ids>[^\]]*)\]'))
def _pruned_kids(ctx, ids):
    expected = {int(x.strip()) for x in ids.split(",") if x.strip()}
    actual = {c["_id"] for c in ctx["pruned"]["children"]}
    assert actual == expected


@then("裁剪结果应当为空对象")
def _pruned_empty(ctx):
    assert ctx["pruned"] == {}


@then(parsers.parse("校验结果应当为 {flag}"))
def _perm_flag(ctx, flag):
    assert ctx["topo_perm"] is (flag.lower() == "true")
