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


def _patch_translations(monkeypatch, mapping):
    """让 list 接口里的 LanguageLoader.get 按 mapping 返回译文，未命中走 default。"""
    from apps.monitor.views import monitor_object as mo_views

    monkeypatch.setattr(
        mo_views.LanguageLoader,
        "get",
        lambda self, key, default=None: mapping.get(key, default),
    )


@pytest.mark.django_db
def test_list_translates_display_field_name_when_not_customized(api_client, host_with_metric, monkeypatch):
    """未自定义的展示列：列名按绑定指标的翻译名覆盖（复用指标翻译，跟随账号语言）。"""
    obj = host_with_metric
    obj.display_fields = [
        {"name": "CPU Usage", "sort_order": 0,
         "metrics": [{"plugin": "UTPlugin", "metric": "cpu_usage_total"}]}
    ]
    obj.display_fields_customized = False
    obj.save(update_fields=["display_fields", "display_fields_customized"])

    _patch_translations(monkeypatch, {
        "monitor_object_metric.UTHost.cpu_usage_total.name": "CPU使用率译",
    })
    resp = api_client.get("/api/v1/monitor/api/monitor_object/")
    assert resp.status_code == 200
    target = next(o for o in resp.json()["data"] if o["id"] == obj.id)
    assert target["display_fields"][0]["name"] == "CPU使用率译"


@pytest.mark.django_db
def test_list_keeps_display_field_name_when_customized(api_client, host_with_metric, monkeypatch):
    """用户自定义过的展示列：列名保留原文，不被翻译覆盖。"""
    obj = host_with_metric
    obj.display_fields = [
        {"name": "我的自定义列", "sort_order": 0,
         "metrics": [{"plugin": "UTPlugin", "metric": "cpu_usage_total"}]}
    ]
    obj.display_fields_customized = True
    obj.save(update_fields=["display_fields", "display_fields_customized"])

    _patch_translations(monkeypatch, {
        "monitor_object_metric.UTHost.cpu_usage_total.name": "CPU使用率译",
    })
    resp = api_client.get("/api/v1/monitor/api/monitor_object/")
    assert resp.status_code == 200
    target = next(o for o in resp.json()["data"] if o["id"] == obj.id)
    assert target["display_fields"][0]["name"] == "我的自定义列"


@pytest.mark.django_db
def test_list_keeps_seed_name_when_translation_missing(api_client, host_with_metric, monkeypatch):
    """无译文时保留种子英文列名（兜底）。"""
    obj = host_with_metric
    obj.display_fields = [
        {"name": "CPU Usage", "sort_order": 0,
         "metrics": [{"plugin": "UTPlugin", "metric": "cpu_usage_total"}]}
    ]
    obj.display_fields_customized = False
    obj.save(update_fields=["display_fields", "display_fields_customized"])

    _patch_translations(monkeypatch, {})  # 全部未命中
    resp = api_client.get("/api/v1/monitor/api/monitor_object/")
    assert resp.status_code == 200
    target = next(o for o in resp.json()["data"] if o["id"] == obj.id)
    assert target["display_fields"][0]["name"] == "CPU Usage"
