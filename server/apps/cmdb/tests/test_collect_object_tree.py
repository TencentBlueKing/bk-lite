"""CMDB 采集对象树覆盖测试。

对照 spec/prd/CMDB·自动采集：内置采集对象树合并企业版扩展、按 model_id 查询采集元数据。
"""

import sys
import types

import pytest

from apps.cmdb.services.collect_object_tree import (
    _get_enterprise_collect_obj_tree,
    _normalize_enterprise_children,
    _normalize_enterprise_groups,
    get_collect_obj_tree,
    get_collect_object_meta,
)


# --------------------------------------------------------------------------
# normalize helpers
# --------------------------------------------------------------------------


def test_normalize_groups_variants():
    assert _normalize_enterprise_groups([]) == []
    assert _normalize_enterprise_groups({"id": "x"}) == [{"id": "x"}]
    assert _normalize_enterprise_groups([{"id": "x"}]) == [{"id": "x"}]
    assert _normalize_enterprise_groups("bad") == []
    assert _normalize_enterprise_groups(None) == []


def test_normalize_children_variants():
    assert _normalize_enterprise_children([]) == []
    assert _normalize_enterprise_children({"model_id": "a"}) == [{"model_id": "a"}]
    assert _normalize_enterprise_children([{"model_id": "a"}]) == [{"model_id": "a"}]
    assert _normalize_enterprise_children("bad") == []
    assert _normalize_enterprise_children(None) == []


# --------------------------------------------------------------------------
# _get_enterprise_collect_obj_tree
# --------------------------------------------------------------------------


def test_get_enterprise_collect_obj_tree_missing():
    # 默认无 apps.cmdb.enterprise.tree 模块 → 返回 []
    sys.modules.pop("apps.cmdb.enterprise.tree", None)
    assert _get_enterprise_collect_obj_tree() == []


def test_get_enterprise_collect_obj_tree_present(monkeypatch):
    fake = types.ModuleType("apps.cmdb.enterprise.tree")
    fake.ENTERPRISE_COLLECT_OBJ_TREE = [{"id": "x"}]
    monkeypatch.setitem(sys.modules, "apps.cmdb.enterprise.tree", fake)
    out = _get_enterprise_collect_obj_tree()
    assert out == [{"id": "x"}]


# --------------------------------------------------------------------------
# get_collect_obj_tree
# --------------------------------------------------------------------------


def test_get_collect_obj_tree_no_enterprise(monkeypatch):
    sys.modules.pop("apps.cmdb.enterprise.tree", None)
    tree = get_collect_obj_tree()
    assert isinstance(tree, list)
    assert len(tree) > 0


def test_get_collect_obj_tree_merge_enterprise(monkeypatch):
    base_tree = get_collect_obj_tree()
    category_id = base_tree[0]["id"]
    fake = types.ModuleType("apps.cmdb.enterprise.tree")
    fake.ENTERPRISE_COLLECT_OBJ_TREE = [
        {"id": category_id, "children": [{"model_id": "_ent_new_model", "label": "企业新增"}]}
    ]
    monkeypatch.setitem(sys.modules, "apps.cmdb.enterprise.tree", fake)
    merged = get_collect_obj_tree()
    cat = next(c for c in merged if c["id"] == category_id)
    assert any(c.get("model_id") == "_ent_new_model" for c in cat["children"])


def test_get_collect_obj_tree_merge_replaces_duplicate(monkeypatch):
    base_tree = get_collect_obj_tree()
    cat = base_tree[0]
    if not cat.get("children"):
        pytest.skip("base category has no children")
    existing_model_id = cat["children"][0].get("model_id")
    if not existing_model_id:
        pytest.skip("first child lacks model_id")
    fake = types.ModuleType("apps.cmdb.enterprise.tree")
    fake.ENTERPRISE_COLLECT_OBJ_TREE = {
        "id": cat["id"],
        "children": {"model_id": existing_model_id, "label": "替换"},
    }
    monkeypatch.setitem(sys.modules, "apps.cmdb.enterprise.tree", fake)
    merged = get_collect_obj_tree()
    mcat = next(c for c in merged if c["id"] == cat["id"])
    target = next(c for c in mcat["children"] if c.get("model_id") == existing_model_id)
    assert target["label"] == "替换"


def test_get_collect_obj_tree_skip_invalid_enterprise(monkeypatch):
    fake = types.ModuleType("apps.cmdb.enterprise.tree")
    fake.ENTERPRISE_COLLECT_OBJ_TREE = [
        {},  # 无 id
        {"id": "_absent_cat"},  # 不存在的分类
    ]
    monkeypatch.setitem(sys.modules, "apps.cmdb.enterprise.tree", fake)
    tree = get_collect_obj_tree()
    assert isinstance(tree, list)


# --------------------------------------------------------------------------
# get_collect_object_meta
# --------------------------------------------------------------------------


def test_get_collect_object_meta_found():
    tree = get_collect_obj_tree()
    first_child = None
    for cat in tree:
        for child in cat.get("children", []):
            if child.get("model_id"):
                first_child = child
                break
        if first_child:
            break
    if not first_child:
        pytest.skip("no child with model_id in tree")
    meta = get_collect_object_meta(first_child["model_id"])
    assert meta.get("model_id") == first_child["model_id"]


def test_get_collect_object_meta_missing():
    assert get_collect_object_meta("_unknown_xyz_") == {}


def test_get_collect_object_meta_driver_type_fallback():
    # 当 driver_type 不匹配但有候选 → 返回 fallback
    tree = get_collect_obj_tree()
    target = None
    for cat in tree:
        for child in cat.get("children", []):
            if child.get("model_id"):
                target = child
                break
        if target:
            break
    if not target:
        pytest.skip("tree empty")
    meta = get_collect_object_meta(target["model_id"], driver_type="_nonexistent_driver_")
    assert meta.get("model_id") == target["model_id"]
