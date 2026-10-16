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
        if "ip_addr" in fields:
            wanted = set(fields["ip_addr"]["value"])
            return [row for row in self.rows if row.get("ip_addr") in wanted], None
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


def test_query_task_assets_reuses_inst_name_for_same_cloud_ip():
    default_cloud = {
        "_id": 11,
        "inst_name": "10.10.41.149[default]",
        "ip_addr": "10.10.41.149",
        "cloud": 1,
        "collect_task": "",
        "organization": [1],
    }
    other_cloud = {
        "_id": 12,
        "inst_name": "10.10.41.149[其他云]",
        "ip_addr": "10.10.41.149",
        "cloud": 2,
        "collect_task": "",
        "organization": [1],
    }
    metric = {"inst_name": "demo-host-v2", "ip_addr": "10.10.41.149", "cloud": 1}
    graph = _Graph([default_cloud, other_cloud])

    old, accepted, failed = _cannula()._query_task_assets(graph, "host", [metric])

    assert metric["inst_name"] == "10.10.41.149[default]"
    assert metric["cloud"] == 1
    assert accepted == [metric]
    assert failed == []
    assert old == [default_cloud]
    assert graph.name_queries == [["10.10.41.149[default]"]]


def test_query_task_assets_does_not_guess_cloud_from_ip_alone():
    existing = {
        "_id": 11,
        "inst_name": "10.10.41.149[default]",
        "ip_addr": "10.10.41.149",
        "cloud": 1,
        "collect_task": "",
        "organization": [1],
    }
    metric = {"inst_name": "demo-host-v2", "ip_addr": "10.10.41.149"}
    graph = _Graph([existing])

    _old, accepted, failed = _cannula()._query_task_assets(graph, "host", [metric])

    assert metric == {"inst_name": "demo-host-v2", "ip_addr": "10.10.41.149"}
    assert accepted == [metric]
    assert failed == []
    assert graph.name_queries == [["demo-host-v2"]]


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
