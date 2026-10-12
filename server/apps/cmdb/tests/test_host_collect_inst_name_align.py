"""主机采集进对比前，沿用已有实例名。"""

import pytest

from apps.cmdb.collection.metrics_cannula import MetricsCannula

pytestmark = pytest.mark.unit


class _Graph:
    def __init__(self, rows):
        self.rows = rows
        self.name_queries = []

    def query_entity(self, _label, params):
        fields = {item["field"]: item for item in params}
        if "collect_task" in fields:
            task_id = str(fields["collect_task"]["value"])
            return [row for row in self.rows if str(row.get("collect_task")) == task_id], None
        if "inst_name" in fields:
            wanted = list(fields["inst_name"]["value"])
            self.name_queries.append(wanted)
            return [row for row in self.rows if row.get("inst_name") in wanted], None
        return [], None


def _cannula():
    return MetricsCannula(
        inst_id=None,
        organization=[1],
        inst_name="",
        task_id=9,
        collect_plugin=object,
        default_metrics={"host": []},
    )


def test_query_task_assets_uses_business_name_before_conflict_lookup():
    renamed = {
        "_id": 11,
        "inst_name": "订单服务",
        "ip_addr": "10.0.0.1",
        "cloud": 2,
        "collect_task": "9",
        "organization": [1],
    }
    taken = {
        "_id": 22,
        "inst_name": "10.0.0.1[生产云]",
        "ip_addr": "10.0.0.9",
        "cloud": 2,
        "collect_task": "8",
        "organization": [1],
    }
    metric = {"inst_name": "10.0.0.1[生产云]", "ip_addr": "10.0.0.1", "cloud": 2}
    graph = _Graph([renamed, taken])

    _old, accepted, failed = _cannula()._query_task_assets(graph, "host", [metric])

    assert metric["inst_name"] == "订单服务"
    assert accepted == [metric]
    assert failed == []
    assert graph.name_queries == [["订单服务"]]


def test_query_task_assets_keeps_generated_name_when_ip_changes():
    renamed = {
        "_id": 11,
        "inst_name": "订单服务",
        "ip_addr": "10.0.0.1",
        "cloud": 2,
        "collect_task": "9",
        "organization": [1],
    }
    metric = {"inst_name": "10.0.0.8[生产云]", "ip_addr": "10.0.0.8", "cloud": 2}
    graph = _Graph([renamed])

    _old, accepted, failed = _cannula()._query_task_assets(graph, "host", [metric])

    assert metric["inst_name"] == "10.0.0.8[生产云]"
    assert accepted == [metric]
    assert failed == []
    assert graph.name_queries == [["10.0.0.8[生产云]"]]


def test_query_task_assets_does_not_align_other_models():
    existing = {
        "_id": 11,
        "inst_name": "订单服务",
        "ip_addr": "10.0.0.1",
        "cloud": 2,
        "collect_task": "9",
        "organization": [1],
    }
    metric = {"inst_name": "10.0.0.1[生产云]", "ip_addr": "10.0.0.1", "cloud": 2}
    graph = _Graph([existing])

    _cannula()._query_task_assets(graph, "disk", [metric])

    assert metric["inst_name"] == "10.0.0.1[生产云]"
    assert graph.name_queries == [["10.0.0.1[生产云]"]]
