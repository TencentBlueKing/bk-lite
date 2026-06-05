"""聚合维度解析器覆盖测试。

对照 spec/prd/告警中心·配置：相关性规则按应用/基础设施/实例维度降级聚合。
"""

from apps.alerts.aggregation.core.dimension_resolver import DimensionResolver, DimensionType


def test_custom_with_dimensions():
    assert DimensionResolver.resolve_dimensions_for_strategy("custom", ["a", "b"]) == [["a", "b"]]


def test_custom_without_dimensions():
    assert DimensionResolver.resolve_dimensions_for_strategy("custom", None) == [["event_id"]]


def test_application_first_fallback_chain():
    result = DimensionResolver.resolve_dimensions_for_strategy(DimensionType.APPLICATION.value)
    assert result == [["service"], ["location"], ["resource_name"], ["event_id"]]


def test_infrastructure_first():
    result = DimensionResolver.resolve_dimensions_for_strategy(DimensionType.INFRASTRUCTURE.value)
    assert result == [["location"], ["resource_name"], ["event_id"]]


def test_instance_first():
    result = DimensionResolver.resolve_dimensions_for_strategy(DimensionType.INSTANCE.value)
    assert result == [["resource_name"], ["event_id"]]


def test_unknown_defaults_to_instance():
    result = DimensionResolver.resolve_dimensions_for_strategy("garbage")
    assert result == [["resource_name"], ["event_id"]]
