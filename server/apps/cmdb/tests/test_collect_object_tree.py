"""CMDB 采集对象树覆盖测试。

对照 spec/prd/CMDB·自动采集：内置采集对象树合并企业版扩展、按 model_id 查询采集元数据。
"""

import pytest

from apps.cmdb.collect.extensions import CollectEnterpriseExtension
from apps.cmdb.services.collect_object_tree import (
    _get_enterprise_collect_obj_tree,
    _normalize_enterprise_children,
    _normalize_enterprise_groups,
    get_collect_obj_tree,
    get_collect_object_meta,
)


def _patch_collect_extension(monkeypatch, collect_tree):
    """把 collect 门面打补丁为返回给定采集树（模拟企业 provider）。"""
    monkeypatch.setattr(
        "apps.cmdb.services.collect_object_tree.get_collect_enterprise_extension",
        lambda: CollectEnterpriseExtension(collect_tree=collect_tree),
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


def test_get_enterprise_collect_obj_tree_missing(monkeypatch):
    # 门面返回空契约（模拟无企业 provider）→ 返回 []
    _patch_collect_extension(monkeypatch, [])
    assert _get_enterprise_collect_obj_tree() == []


def test_get_enterprise_collect_obj_tree_present(monkeypatch):
    _patch_collect_extension(monkeypatch, [{"id": "x"}])
    out = _get_enterprise_collect_obj_tree()
    assert out == [{"id": "x"}]


# --------------------------------------------------------------------------
# get_collect_obj_tree
# --------------------------------------------------------------------------


def test_get_collect_obj_tree_no_enterprise(monkeypatch):
    _patch_collect_extension(monkeypatch, [])
    tree = get_collect_obj_tree()
    assert isinstance(tree, list)
    assert len(tree) > 0


def test_get_collect_obj_tree_merge_enterprise(monkeypatch):
    base_tree = get_collect_obj_tree()
    category_id = base_tree[0]["id"]
    _patch_collect_extension(
        monkeypatch,
        [{"id": category_id, "children": [{"model_id": "_ent_new_model", "label": "企业新增"}]}],
    )
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
    _patch_collect_extension(
        monkeypatch,
        {"id": cat["id"], "children": {"model_id": existing_model_id, "label": "替换"}},
    )
    merged = get_collect_obj_tree()
    mcat = next(c for c in merged if c["id"] == cat["id"])
    target = next(c for c in mcat["children"] if c.get("model_id") == existing_model_id)
    assert target["label"] == "替换"


def test_get_collect_obj_tree_skip_invalid_enterprise(monkeypatch):
    _patch_collect_extension(
        monkeypatch,
        [
            {},  # 无 id
            {"id": "_absent_cat"},  # 不存在的分类
        ],
    )
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
