import importlib.util
import sys
import types
from pathlib import Path

import pytest

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject
from apps.monitor.services.flow_access_guide import FlowAccessGuideService
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.monitor.services.template_access_guide import TemplateAccessGuideService


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_flow_guide_returns_protocol_endpoint_and_sampling_docs(monkeypatch, db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    monkeypatch.setattr(
        FlowAccessGuideService,
        "get_listener_endpoint",
        lambda protocol, cloud_region_id: f"udp://10.0.0.1:{2055 if protocol == 'netflow' else 6343}",
    )

    doc = FlowAccessGuideService.build_document(
        protocol="netflow",
        cloud_region_id=1,
        monitor_object=switch_object,
    )

    assert doc["protocol"] == "netflow"
    assert doc["endpoint"] == "udp://10.0.0.1:2055"
    assert "effective_sampling_rate" in doc["sampling_rule"]


def test_build_flow_guide_does_not_lock_monitor_object(monkeypatch, db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    monkeypatch.setattr(
        FlowAccessGuideService,
        "get_listener_endpoint",
        lambda protocol, cloud_region_id: "udp://10.0.0.1:2055",
    )
    monkeypatch.setattr(
        "apps.monitor.services.flow_access_guide.FlowOnboardingService.lock_monitor_object",
        lambda **kwargs: pytest.fail("build_document should not lock monitor objects"),
    )

    doc = FlowAccessGuideService.build_document(
        protocol="netflow",
        cloud_region_id=1,
        monitor_object=switch_object,
    )

    assert doc["monitor_object_id"] == switch_object.id


def test_detect_status_uses_protocol_scoped_recent_data_query(db, monkeypatch):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )
    queries = []

    class StubVictoriaMetricsAPI:
        def query(self, query):
            queries.append(query)
            return {
                "data": {
                    "result": [
                        {
                            "metric": {"samplingRate": "2048"},
                            "value": [1712052000, "1"],
                        }
                    ]
                }
            }

    monkeypatch.setattr("apps.monitor.services.flow_onboarding.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = FlowOnboardingService.detect_status(
        instance_id=instance.id,
        protocol="netflow",
        monitor_object_id=switch_object.id,
        time_window="10m",
    )

    assert queries == ["any({instance_id='flow-device-1', collect_type='netflow'}[10m])"]
    assert result == {
        "success": True,
        "protocol": "netflow",
        "instance_id": instance.id,
        "last_seen_at": 1712052000,
        "effective_sampling_rate": 2048,
        "sampling_rate_source": "normalized_from_samplingRate",
    }


def test_detect_status_returns_unsuccessful_when_recent_data_is_missing(db, monkeypatch):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    instance = MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.13",
        fallback_sampling_rate=1000,
        enabled_protocols=["sflow"],
    )

    class StubVictoriaMetricsAPI:
        def query(self, query):
            return {"data": {"result": []}}

    monkeypatch.setattr("apps.monitor.services.flow_onboarding.VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = FlowOnboardingService.detect_status(
        instance_id=instance.id,
        protocol="sflow",
        monitor_object_id=switch_object.id,
    )

    assert result == {
        "success": False,
        "protocol": "sflow",
        "instance_id": instance.id,
        "last_seen_at": None,
        "effective_sampling_rate": 1000,
        "sampling_rate_source": "fallback_sampling_rate",
    }


def test_flow_access_guide_normalizes_payload_before_service_call(monkeypatch, db):
    calls = {}

    class ViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def build_document(**kwargs):
        calls["build_document"] = kwargs
        return kwargs

    _install_module(monkeypatch, "rest_framework.viewsets", ViewSet=ViewSet)
    _install_module(monkeypatch, "rest_framework.decorators", action=action)
    _install_module(
        monkeypatch,
        "apps.core.utils.web_utils",
        WebUtils=types.SimpleNamespace(response_success=lambda data=None: data),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.services.flow_onboarding",
        FlowOnboardingService=types.SimpleNamespace(
            SUPPORTED_PROTOCOLS={"netflow", "sflow"},
            lock_monitor_object=lambda **kwargs: "Switch",
        ),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.services.flow_access_guide",
        FlowAccessGuideService=types.SimpleNamespace(build_document=build_document),
    )
    _install_module(monkeypatch, "apps.monitor.services.manual_collect", ManualCollectService=object)
    _install_module(
        monkeypatch,
        "apps.monitor.views.monitor_instance",
        _build_actor_context=lambda request: {"current_team": 7},
        _ensure_operate_instances=lambda request, instance_ids, received_actor_context=None: instance_ids,
        _ensure_target_organizations=lambda organizations, received_actor_context: None,
    )
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)

    module = _load_module(
        "manual_collect_view_test_module_flow_access_guide",
        Path(__file__).resolve().parents[1] / "views" / "manual_collect.py",
    )

    request = types.SimpleNamespace(
        data={
            "monitor_object_id": "1",
            "protocol": "netflow",
            "cloud_region_id": "2",
        }
    )

    response = module.ManualCollect().flow_access_guide(request)

    assert response == calls["build_document"]
    assert calls["build_document"] == {
        "monitor_object_id": 1,
        "protocol": "netflow",
        "cloud_region_id": 2,
    }


def test_flow_detect_status_checks_operate_permission_before_service_call(monkeypatch, db):
    calls = {}
    actor_context = {"current_team": 7}

    class ViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def detect_status(**kwargs):
        calls["detect_status"] = kwargs
        return {"success": True}

    def _build_actor_context(request):
        return actor_context

    def _ensure_operate_instances(request, instance_ids, received_actor_context=None):
        calls["operate_args"] = (request, instance_ids, received_actor_context)
        return instance_ids

    _install_module(monkeypatch, "rest_framework.viewsets", ViewSet=ViewSet)
    _install_module(monkeypatch, "rest_framework.decorators", action=action)
    _install_module(
        monkeypatch,
        "apps.core.utils.web_utils",
        WebUtils=types.SimpleNamespace(response_success=lambda data=None: data),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.services.flow_onboarding",
        FlowOnboardingService=types.SimpleNamespace(
            SUPPORTED_PROTOCOLS={"netflow", "sflow"},
            detect_status=detect_status,
        ),
    )
    _install_module(monkeypatch, "apps.monitor.services.manual_collect", ManualCollectService=object)
    _install_module(
        monkeypatch,
        "apps.monitor.services.flow_access_guide",
        FlowAccessGuideService=types.SimpleNamespace(build_document=lambda **kwargs: kwargs),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.views.monitor_instance",
        _build_actor_context=_build_actor_context,
        _ensure_operate_instances=_ensure_operate_instances,
        _ensure_target_organizations=lambda organizations, received_actor_context: None,
    )
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)

    module = _load_module(
        "manual_collect_view_test_module_flow_detect_status",
        Path(__file__).resolve().parents[1] / "views" / "manual_collect.py",
    )

    request = types.SimpleNamespace(
        data={
            "instance_id": "inst-a",
            "monitor_object_id": "1",
            "protocol": "sflow",
            "time_window": "10m",
        }
    )

    response = module.ManualCollect().flow_detect_status(request)

    assert response == {"success": True}
    assert calls["operate_args"] == (request, ["inst-a"], actor_context)
    assert calls["detect_status"] == {
        "instance_id": "inst-a",
        "monitor_object_id": 1,
        "protocol": "sflow",
        "time_window": "10m",
    }


def test_flow_detect_status_rejects_invalid_time_window(monkeypatch, db):
    class ViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    _install_module(monkeypatch, "rest_framework.viewsets", ViewSet=ViewSet)
    _install_module(monkeypatch, "rest_framework.decorators", action=action)
    _install_module(
        monkeypatch,
        "apps.core.utils.web_utils",
        WebUtils=types.SimpleNamespace(response_success=lambda data=None: data),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.services.flow_onboarding",
        FlowOnboardingService=types.SimpleNamespace(
            SUPPORTED_PROTOCOLS={"netflow", "sflow"},
            detect_status=lambda **kwargs: kwargs,
        ),
    )
    _install_module(monkeypatch, "apps.monitor.services.manual_collect", ManualCollectService=object)
    _install_module(
        monkeypatch,
        "apps.monitor.services.flow_access_guide",
        FlowAccessGuideService=types.SimpleNamespace(build_document=lambda **kwargs: kwargs),
    )
    _install_module(
        monkeypatch,
        "apps.monitor.views.monitor_instance",
        _build_actor_context=lambda request: {"current_team": 7},
        _ensure_operate_instances=lambda request, instance_ids, received_actor_context=None: instance_ids,
        _ensure_target_organizations=lambda organizations, received_actor_context: None,
    )
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)

    module = _load_module(
        "manual_collect_view_test_module_flow_detect_status_invalid_window",
        Path(__file__).resolve().parents[1] / "views" / "manual_collect.py",
    )

    request = types.SimpleNamespace(
        data={
            "instance_id": "inst-a",
            "monitor_object_id": "1",
            "protocol": "netflow",
            "time_window": "10m]) or on() vector(1)",
        }
    )

    with pytest.raises(ValidationAppException, match="Field time_window must be a valid time window"):
        module.ManualCollect().flow_detect_status(request)


def test_template_access_guide_keeps_non_flow_timestamp_example_stable(monkeypatch):
    monitor_object = types.SimpleNamespace(
        id=101,
        name="Host",
        display_name="Host",
        instance_id_keys=["bk_target_ip"],
    )
    plugin = types.SimpleNamespace(
        template_id="custom_api_demo",
        display_name="Custom API Demo",
        name="custom_api_demo",
        description="custom api plugin",
        pk=208,
        monitor_object=types.SimpleNamespace(values_list=lambda *args, **kwargs: [monitor_object.id]),
    )
    metric_rows = [
        {
            "name": "cpu_usage",
            "display_name": "CPU Usage",
            "description": "demo metric",
            "unit": "%",
            "data_type": "gauge",
            "dimensions": [],
        }
    ]

    class StubMonitorObjectQuerySet:
        def order_by(self, *args):
            return self

        def first(self):
            return monitor_object

    class StubMetricQuerySet:
        def order_by(self, *args):
            return self

        def values(self, *args):
            return metric_rows

    monkeypatch.setattr(
        "apps.monitor.services.template_access_guide.MonitorObject",
        types.SimpleNamespace(
            _default_manager=types.SimpleNamespace(filter=lambda **kwargs: StubMonitorObjectQuerySet())
        ),
    )
    monkeypatch.setattr(
        "apps.monitor.services.template_access_guide.Metric",
        types.SimpleNamespace(_default_manager=types.SimpleNamespace(filter=lambda **kwargs: StubMetricQuerySet())),
    )
    monkeypatch.setattr(
        TemplateAccessGuideService,
        "get_telegraf_listener_endpoint",
        staticmethod(lambda cloud_region_id: f"https://region-{cloud_region_id}.example.com/telegraf/api"),
    )

    document = TemplateAccessGuideService.get_template_document(
        plugin=plugin,
        organization_id=7,
        cloud_region_id=2,
    )

    assert TemplateAccessGuideService.DEFAULT_TIMESTAMP_MS_EXAMPLE == 1712052000000
    assert document["line_protocol_example_without_timestamp"] == (
        "cpu_usage,organization_id=7,instance_type=Host,plugin_id=custom_api_demo,bk_target_ip=demo_bk_target_ip value=1"
    )
    assert (
        document["line_protocol_example_with_timestamp_ms"]
        == f"{document['line_protocol_example_without_timestamp']} 1712052000000"
    )
