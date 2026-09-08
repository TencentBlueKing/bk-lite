from types import SimpleNamespace

import pytest

from apps.monitor.services.authorized_metric_query import _render_metric_query

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
    query = _render_metric_query(_metric(), ['instance_id=~"host"'], None)
    assert query == 'avg(cpu_usage{instance_id=~"host"}) by (instance_id, mode)'


def test_default_avg_without_dimensions_groups_only_by_instance():
    query = _render_metric_query(_metric(dimensions=[]), ['instance_id=~"host"'], None)
    assert query == 'avg(cpu_usage{instance_id=~"host"}) by (instance_id)'


def test_sum_aggregation_still_groups_only_by_instance_keys():
    query = _render_metric_query(_metric(), ['instance_id=~"host"'], "SUM")
    assert query == 'sum(cpu_usage{instance_id=~"host"}) by (instance_id)'
