import pytest
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.plugin import MonitorPlugin


@pytest.fixture
def host_with_metric(db):
    obj = MonitorObject.objects.create(name="UTHost", level="base")
    plugin = MonitorPlugin.objects.create(name="UTPlugin")
    plugin.monitor_object.add(obj)
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="Base")
    Metric.objects.create(monitor_object=obj, monitor_plugin=plugin, metric_group=group,
                          name="cpu_usage_total", display_name="CPU使用率", query="x{__$labels__}",
                          unit="percent", data_type="Number")
    return obj


@pytest.mark.django_db
def test_save_display_fields_sets_customized(api_client, host_with_metric):
    obj = host_with_metric
    payload = {"display_fields": [
        {"name": "CPU使用率", "sort_order": 0,
         "metrics": [{"plugin": "UTPlugin", "metric": "cpu_usage_total"}]}
    ]}
    resp = api_client.post(f"/api/v1/monitor/api/monitor_object/{obj.id}/display_fields/", payload, format="json")
    assert resp.status_code == 200
    obj.refresh_from_db()
    # 断言持久化的是规整后的输出（与接口返回一致），而非原始 payload
    assert obj.display_fields == resp.json()["data"]
    assert obj.display_fields == payload["display_fields"]
    assert obj.display_fields_customized is True


@pytest.mark.django_db
def test_save_display_fields_rejects_unknown_metric(api_client, host_with_metric):
    obj = host_with_metric
    payload = {"display_fields": [
        {"name": "X", "sort_order": 0, "metrics": [{"plugin": "UTPlugin", "metric": "does_not_exist"}]}
    ]}
    resp = api_client.post(f"/api/v1/monitor/api/monitor_object/{obj.id}/display_fields/", payload, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_save_display_fields_rejects_empty_name(api_client, host_with_metric):
    obj = host_with_metric
    payload = {"display_fields": [
        {"name": "", "sort_order": 0, "metrics": [{"plugin": "UTPlugin", "metric": "cpu_usage_total"}]}
    ]}
    resp = api_client.post(f"/api/v1/monitor/api/monitor_object/{obj.id}/display_fields/", payload, format="json")
    assert resp.status_code == 400
