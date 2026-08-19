"""治理门禁（unit）：双租户覆盖登记完整性。

本测试即 CI 门禁：新增暴露端点未登记双租户测试、或登记引用失效时失败。
"""

import importlib

import pytest

from apps.core.openapi.registry import OpenAPIRegistry, default_registry
from apps.core.openapi.tests.tenant_coverage import TENANT_ISOLATION_COVERAGE

pytestmark = pytest.mark.unit


def find_uncovered(endpoints, coverage: dict):
    """返回未登记双租户测试的端点 path 列表（纯函数，便于自测）。"""
    return sorted(
        {ep.path for ep in endpoints} - set(coverage)
    )


def resolve_reference(ref: str) -> bool:
    """校验 "module.path::function" 形式的测试引用真实存在。"""
    module_path, _, func_name = ref.partition("::")
    if not func_name:
        return False
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        return False
    return callable(getattr(module, func_name, None))


def test_every_exposed_endpoint_registered_in_coverage():
    uncovered = find_uncovered(default_registry.endpoints(), TENANT_ISOLATION_COVERAGE)
    assert not uncovered, (
        f"以下暴露端点未登记双租户测试（安全红线 4，暴露的准入条件）：{uncovered}。"
        "请补充测试并登记到 apps/core/openapi/tests/tenant_coverage.py"
    )


def test_every_coverage_reference_resolves():
    broken = [
        ref
        for refs in TENANT_ISOLATION_COVERAGE.values()
        for ref in refs
        if not resolve_reference(ref)
    ]
    assert not broken, f"以下登记的测试引用无法解析（测试被移动或删除？）：{broken}"


def test_every_coverage_path_has_at_least_one_reference():
    empty = [path for path, refs in TENANT_ISOLATION_COVERAGE.items() if not refs]
    assert not empty, f"以下登记项没有任何测试引用：{empty}"


def test_stale_coverage_entries_flagged():
    """登记表中不存在于注册表的 path 视为陈旧登记（端点被删后应同步清理）。"""
    registered = {ep.path for ep in default_registry.endpoints()}
    stale = sorted(set(TENANT_ISOLATION_COVERAGE) - registered)
    assert not stale, f"以下登记项对应的端点已不存在：{stale}"


def test_find_uncovered_detects_missing_entry():
    """门禁自验证：未登记的端点必须被检出。"""
    from rest_framework import serializers

    from apps.core.openapi.serializers import OpenAPIRequestSerializer

    class S(OpenAPIRequestSerializer):
        name = serializers.CharField()

    def func(name, *, team=None):
        return {}

    reg = OpenAPIRegistry()
    reg.register(
        path="demo/uncovered",
        method="GET",
        serializer_class=S,
        func=func,
        inject="team_list",
    )
    assert find_uncovered(reg.endpoints(), TENANT_ISOLATION_COVERAGE) == [
        "demo/uncovered"
    ]
