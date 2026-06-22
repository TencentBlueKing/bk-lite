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


_METRIC_KEY = "monitor_object_metric.UTHost.cpu_usage_total.name"


def _patch_translations(monkeypatch, mapping):
    """mock list 接口里的 LanguageLoader.get 按 mapping 返回译文，未命中走 default。"""
    from apps.monitor.views import monitor_object as mo_views

    monkeypatch.setattr(
        mo_views.LanguageLoader,
        "get",
        lambda self, key, default=None: mapping.get(key, default),
    )


def _get_object(resp, obj_id):
    assert resp.status_code == 200
    return next(o for o in resp.json()["data"] if o["id"] == obj_id)


@pytest.mark.django_db
def test_list_translates_column_to_metric_name(api_client, host_with_metric, monkeypatch):
    """列名一律取绑定指标的当前语言译名（跟随账号语言）；即使种子名/已 customized 也照译（回归用例）。"""
    obj = host_with_metric
    obj.display_fields = [
        {"name": "Service Uptime", "sort_order": 0,  # 种子标签，故意 != 指标译名
         "metrics": [{"plugin": "UTPlugin", "metric": "cpu_usage_total"}]}
    ]
    obj.display_fields_customized = True  # 用户在弹窗里编辑过，仍应翻译
    obj.save(update_fields=["display_fields", "display_fields_customized"])

    _patch_translations(monkeypatch, {_METRIC_KEY: "CPU使用率译"})
    target = _get_object(api_client.get("/api/v1/monitor/api/monitor_object/"), obj.id)
    assert target["display_fields"][0]["name"] == "CPU使用率译"


@pytest.mark.django_db
def test_list_keeps_name_when_translation_missing(api_client, host_with_metric, monkeypatch):
    """无译文时保留原列名（兜底）。"""
    obj = host_with_metric
    obj.display_fields = [
        {"name": "Service Uptime", "sort_order": 0,
         "metrics": [{"plugin": "UTPlugin", "metric": "cpu_usage_total"}]}
    ]
    obj.save(update_fields=["display_fields"])

    _patch_translations(monkeypatch, {})  # 未命中
    target = _get_object(api_client.get("/api/v1/monitor/api/monitor_object/"), obj.id)
    assert target["display_fields"][0]["name"] == "Service Uptime"


@pytest.mark.django_db
def test_list_keeps_name_when_no_metric_binding(api_client, host_with_metric, monkeypatch):
    """无绑定指标的列：无可翻译来源，保留原列名。"""
    obj = host_with_metric
    obj.display_fields = [{"name": "纯文本列", "sort_order": 0, "metrics": []}]
    obj.save(update_fields=["display_fields"])

    _patch_translations(monkeypatch, {_METRIC_KEY: "CPU使用率译"})
    target = _get_object(api_client.get("/api/v1/monitor/api/monitor_object/"), obj.id)
    assert target["display_fields"][0]["name"] == "纯文本列"
