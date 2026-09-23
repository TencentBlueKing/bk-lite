"""资产列表关键词搜索：按对象框定名称/IP，以及拨测、进程的补充字段。"""

import pytest

from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject
from apps.monitor.services.monitor_instance import InstanceSearch
from apps.monitor.services.monitor_object import MonitorObjectService

pytestmark = pytest.mark.django_db

PROBE_COLUMNS = [
    {"fact": "collector.nodes", "title": "monitor.views.probeNodes", "order": 10},
    {"fact": "probe.target", "title": "monitor.views.probeTarget", "order": 20},
]


def _object(name, **kwargs):
    defaults = {
        "level": "base",
        "default_metric": "up",
        "instance_id_keys": ["instance_id"],
    }
    defaults.update(kwargs)
    return MonitorObject.objects.create(name=name, **defaults)


def _instance(obj, pk, name, **kwargs):
    return MonitorInstance.objects.create(id=pk, name=name, monitor_object=obj, **kwargs)


def _ids(qs):
    return set(qs.values_list("id", flat=True))


def test_keyword_search_matches_name_and_ip_for_ordinary_objects():
    obj = _object("Host")
    named = _instance(obj, "('h1',)", "web-prod", ip="")
    by_model_ip = _instance(obj, "('h2',)", "db-1", ip="10.10.0.8")
    by_fact_ip = _instance(obj, "('h3',)", "cache-1", ip="", summary_facts={"asset.ip": "10.10.0.9"})
    _instance(obj, "('h4',)", "other", ip="192.168.0.1")

    qs = MonitorInstance.objects.filter(monitor_object=obj)
    assert _ids(InstanceSearch.apply_keyword_search(qs, obj, "web-pro")) == {named.id}
    assert _ids(InstanceSearch.apply_keyword_search(qs, obj, "10.10.0.8")) == {by_model_ip.id}
    assert _ids(InstanceSearch.apply_keyword_search(qs, obj, "10.10.0.9")) == {by_fact_ip.id}


def test_keyword_search_does_not_use_probe_fields_on_ordinary_objects():
    obj = _object("Mysql", instance_summary_columns=[{"fact": "asset.ip", "title": "monitor.views.assetIp", "order": 10}])
    _instance(
        obj,
        "('m1',)",
        "mysql-a",
        ip="10.0.0.1",
        summary_facts={"asset.ip": "10.0.0.1", "probe.target": "https://secret.example/health", "collector.nodes": [{"name": "北京节点"}]},
    )
    qs = MonitorInstance.objects.filter(monitor_object=obj)
    assert _ids(InstanceSearch.apply_keyword_search(qs, obj, "secret.example")) == set()
    assert _ids(InstanceSearch.apply_keyword_search(qs, obj, "北京")) == set()
    assert _ids(InstanceSearch.apply_keyword_search(qs, obj, "mysql")) == {"('m1',)"}


def test_probe_keyword_search_matches_node_and_target():
    obj = _object("Website", instance_summary_columns=PROBE_COLUMNS)
    matched = _instance(
        obj,
        "('w1',)",
        "门户探测",
        summary_facts={
            "collector.nodes": [{"id": "n1", "name": "北京节点", "ip": "10.0.0.8"}],
            "probe.target": "https://shop.example.com/health",
        },
    )
    _instance(
        obj,
        "('w2',)",
        "支付探测",
        summary_facts={
            "collector.nodes": [{"id": "n2", "name": "上海节点", "ip": "10.0.1.8"}],
            "probe.target": "https://pay.internal/ping",
        },
    )
    qs = MonitorInstance.objects.filter(monitor_object=obj)
    assert _ids(InstanceSearch.apply_keyword_search(qs, obj, "shop.example")) == {matched.id}
    assert _ids(InstanceSearch.apply_keyword_search(qs, obj, "北京")) == {matched.id}
    assert _ids(InstanceSearch.apply_keyword_search(qs, obj, "10.0.0.8")) == {matched.id}
    assert _ids(InstanceSearch.apply_keyword_search(qs, obj, "门户")) == {matched.id}


def test_process_keyword_search_matches_process_host_name_and_host_ip():
    host_obj = _object("Host")
    process_obj = _object(
        "Process",
        instance_id_keys=["instance_id", "process_name"],
        instance_summary_columns=[{"fact": "asset.ip", "title": "monitor.views.hostIp", "order": 10}],
    )
    _instance(host_obj, "('host-a',)", "web-prod", ip="10.1.2.3", summary_facts={"asset.ip": "10.1.2.3"})
    _instance(host_obj, "('host-b',)", "db-prod", ip="10.9.9.9")
    matched = _instance(
        process_obj,
        "('host-a', 'nginx')",
        "nginx-svc",
        summary_facts={"asset.ip": "10.1.2.3"},
    )
    _instance(
        process_obj,
        "('host-b', 'mysqld')",
        "mysql-svc",
        summary_facts={"asset.ip": "10.9.9.9"},
    )
    qs = MonitorInstance.objects.filter(monitor_object=process_obj)
    assert _ids(InstanceSearch.apply_keyword_search(qs, process_obj, "nginx")) == {matched.id}
    assert _ids(InstanceSearch.apply_keyword_search(qs, process_obj, "nginx-svc")) == {matched.id}
    assert _ids(InstanceSearch.apply_keyword_search(qs, process_obj, "web-prod")) == {matched.id}
    assert _ids(InstanceSearch.apply_keyword_search(qs, process_obj, "10.1.2.3")) == {matched.id}
    assert _ids(InstanceSearch.apply_keyword_search(qs, process_obj, "mysqld")) == {"('host-b', 'mysqld')"}


def test_blank_keyword_does_not_filter():
    obj = _object("Host")
    _instance(obj, "('h1',)", "web-prod")
    qs = MonitorInstance.objects.filter(monitor_object=obj)
    assert InstanceSearch.apply_keyword_search(qs, obj, "  ").count() == 1
    assert InstanceSearch.apply_keyword_search(qs, obj, None).count() == 1


def test_get_objs_v2_uses_keyword_search(monkeypatch):
    obj = _object("Website", instance_summary_columns=PROBE_COLUMNS)
    _instance(
        obj,
        "('w1',)",
        "门户探测",
        summary_facts={"probe.target": "https://shop.example.com/health", "collector.nodes": []},
    )
    _instance(obj, "('w2',)", "支付探测", summary_facts={"probe.target": "https://pay.internal/ping"})
    monkeypatch.setattr("apps.monitor.services.collect_config_update.CollectConfigUpdateService.filter_instance_qs", lambda qs, query_data: qs)
    data = InstanceSearch(
        obj,
        {"name": "shop.example", "page": 1, "page_size": -1},
        qs=MonitorInstance.objects.all(),
    ).get_objs_v2()
    assert data["count"] == 1
    assert data["results"][0]["instance_id"] == "('w1',)"


def test_get_monitor_instance_uses_keyword_search(monkeypatch):
    obj = _object("Host")
    _instance(obj, "('h1',)", "web-prod", ip="10.10.0.8")
    _instance(obj, "('h2',)", "db-1", ip="10.9.9.9")
    monkeypatch.setattr(MonitorObjectService, "get_instances_by_metric", lambda *args, **kwargs: {})
    monkeypatch.setattr(MonitorObjectService, "add_attr", lambda result, visible_organization_ids=None: None)
    data = MonitorObjectService.get_monitor_instance(
        obj.id,
        page=1,
        page_size=-1,
        name="10.10.0.8",
        qs=MonitorInstance.objects.all(),
    )
    assert data["count"] == 1
    assert data["results"][0]["instance_id"] == "('h1',)"
