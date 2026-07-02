"""node_selector 纯函数测试 — 校验节点选择器归一化与合并的真实行为及异常契约。"""
import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.utils.node_selector import (
    normalize_node_selector,
    merge_node_query_with_selector,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("empty", [None, ""])
def test_normalize_empty_returns_empty_dict(empty):
    assert normalize_node_selector(empty) == {}


def test_normalize_non_dict_raises():
    with pytest.raises(BaseAppException, match="必须是对象"):
        normalize_node_selector(["is_container"])


def test_normalize_unsupported_keys_raises_sorted():
    with pytest.raises(BaseAppException, match="zeta"):
        normalize_node_selector({"alpha": 1, "zeta": 2})


def test_normalize_is_container_must_be_bool():
    with pytest.raises(BaseAppException, match="必须是布尔值"):
        normalize_node_selector({"is_container": "true"})


def test_normalize_valid_is_container():
    assert normalize_node_selector({"is_container": True}) == {"is_container": True}
    assert normalize_node_selector({"is_container": False}) == {"is_container": False}


def test_merge_empty_selector_returns_query_unchanged():
    query = {"cloud_region_id": 1}
    assert merge_node_query_with_selector(query, None) == query


def test_merge_fills_missing_key():
    merged = merge_node_query_with_selector({"is_container": None}, {"is_container": True})
    assert merged["is_container"] is True


def test_merge_fills_when_absent():
    merged = merge_node_query_with_selector({}, {"is_container": True})
    assert merged == {"is_container": True}


def test_merge_consistent_value_ok():
    merged = merge_node_query_with_selector({"is_container": True}, {"is_container": True})
    assert merged == {"is_container": True}


def test_merge_conflicting_value_raises():
    with pytest.raises(BaseAppException, match="限制了可选节点范围"):
        merge_node_query_with_selector({"is_container": False}, {"is_container": True})


def test_merge_does_not_mutate_input():
    original = {"is_container": None, "x": 1}
    merge_node_query_with_selector(original, {"is_container": True})
    assert original["is_container"] is None
