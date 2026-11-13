from types import SimpleNamespace

import pytest

from apps.monitor.services.authorized_metric_query import (
    GROUPING_INSTANCE,
    _render_metric_query,
    _select_authorized_instance,
    empty_aggregation_needs_choice,
)

pytestmark = pytest.mark.unit


def _metric(**overrides):
    values = {
        "query": "cpu_usage{__$labels__}",
        "instance_id_keys": ["instance_id"],
        "dimensions": [{"name": "mode"}],
        "monitor_object": SimpleNamespace(instance_id_keys=["instance_id"]),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_default_avg_aggregates_by_instance_and_declared_dimensions():
    query = _render_metric_query(_metric(), [['instance_id=~"host"']], None)
    assert query == 'avg(cpu_usage{instance_id=~"host"}) by (instance_id, mode)'


def test_explicit_instance_grouping_drops_declared_dimensions():
    query = _render_metric_query(_metric(), [['instance_id=~"host"']], None, GROUPING_INSTANCE)
    assert query == 'avg(cpu_usage{instance_id=~"host"}) by (instance_id)'


def test_default_avg_without_dimensions_groups_only_by_instance():
    query = _render_metric_query(_metric(dimensions=[]), [['instance_id=~"host"']], None)
    assert query == 'avg(cpu_usage{instance_id=~"host"}) by (instance_id)'


def test_instance_alias_does_not_select_a_different_existing_instance():
    stored = "('host-1',)"
    logical = "host-1"
    assert _select_authorized_instance(logical, {stored}, {stored}) == stored
    assert _select_authorized_instance(stored, {logical}, {logical}) == logical
    assert _select_authorized_instance(logical, {stored}, {stored, logical}) is None
    assert _select_authorized_instance(stored, {logical}, {stored, logical}) is None
    assert _select_authorized_instance(logical, {logical, stored}, {logical, stored}) == logical


def test_sum_aggregation_still_groups_only_by_instance_keys():
    query = _render_metric_query(_metric(), [['instance_id=~"host"']], "SUM")
    assert query == 'sum(cpu_usage{instance_id=~"host"}) by (instance_id)'


def _disk():
    return _metric(
        dimensions=[
            {"name": "device"},
            {"name": "path"},
            {"name": "fstype"},
        ]
    )


def _pinned_disk():
    return {
        "logic": "AND",
        "items": [
            {"field": "device", "op": "eq", "value": "sda"},
            {"field": "path", "op": "eq", "value": "/"},
            {"field": "fstype", "op": "eq", "value": "ext4"},
        ],
    }


def test_empty_aggregation_is_allowed_when_the_metric_has_no_dimensions():
    assert empty_aggregation_needs_choice(_metric(dimensions=[]), None) is False


def test_empty_aggregation_is_required_while_any_declared_dimension_is_open():
    assert empty_aggregation_needs_choice(_disk(), None) is True
    assert (
        empty_aggregation_needs_choice(
            _disk(),
            {"logic": "AND", "items": [{"field": "device", "op": "eq", "value": "sda"}]},
        )
        is True
    )


def test_equals_on_every_dimension_lets_empty_aggregation_mean_average():
    assert empty_aggregation_needs_choice(_disk(), _pinned_disk()) is False


def test_or_and_regex_do_not_pin_dimensions():
    assert empty_aggregation_needs_choice(_disk(), {"logic": "OR", "items": _pinned_disk()["items"]}) is True
    filters = _pinned_disk()
    filters["items"] = [*filters["items"][:2], {"field": "fstype", "op": "regex", "value": "ext4"}]
    assert empty_aggregation_needs_choice(_disk(), filters) is True
