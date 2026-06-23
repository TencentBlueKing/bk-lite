"""instance_id_keys 纯函数测试 — 归一化与解析的真实行为及 strict 异常契约。"""
import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.utils.instance_id_keys import (
    normalize_instance_id_keys,
    default_monitor_object_instance_id_keys,
    resolve_monitor_object_instance_id_keys,
    resolve_metric_instance_id_keys,
    MISSING_METRIC_INSTANCE_ID_KEYS_ERROR,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("bad", [None, "abc", 123, {"a": 1}])
def test_normalize_non_list_returns_empty(bad):
    assert normalize_instance_id_keys(bad) == []


def test_normalize_strips_and_drops_blank_and_none():
    assert normalize_instance_id_keys(["  a ", None, "", "b", 7]) == ["a", "b", "7"]


def test_default_base_level():
    assert default_monitor_object_instance_id_keys("base", "Host") == ["instance_id"]


def test_default_derivative_with_object_name():
    assert default_monitor_object_instance_id_keys("derivative", "Disk") == ["instance_id", "Disk"]


def test_default_derivative_without_object_name_falls_back():
    assert default_monitor_object_instance_id_keys("derivative", "") == ["instance_id"]


def test_resolve_object_uses_normalized_when_present():
    assert resolve_monitor_object_instance_id_keys(["x", "y"], "derivative", "Disk") == ["x", "y"]


def test_resolve_object_falls_back_to_default():
    assert resolve_monitor_object_instance_id_keys(None, "derivative", "Disk") == ["instance_id", "Disk"]


def test_resolve_metric_prefers_metric_keys():
    assert resolve_metric_instance_id_keys(["m"], ["o"]) == ["m"]


def test_resolve_metric_falls_back_to_object_keys():
    assert resolve_metric_instance_id_keys([], ["o1", "o2"]) == ["o1", "o2"]


def test_resolve_metric_empty_non_strict_returns_empty():
    assert resolve_metric_instance_id_keys([], []) == []


def test_resolve_metric_empty_strict_raises():
    with pytest.raises(BaseAppException, match=MISSING_METRIC_INSTANCE_ID_KEYS_ERROR):
        resolve_metric_instance_id_keys([], [], strict=True)
