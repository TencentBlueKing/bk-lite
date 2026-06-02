import importlib.util
import sys
import types
from pathlib import Path


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


def test_flow_asset_checks_operate_permission_before_binding_instance(monkeypatch):
    calls = {}
    actor_context = {"current_team": 7}

    class ViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def create_or_bind_asset(**kwargs):
        calls["create_or_bind_asset"] = kwargs
        return {"instance_id": kwargs.get("instance_id")}

    def _build_actor_context(request):
        calls["actor_context_request"] = request
        return actor_context

    def _ensure_operate_instances(request, instance_ids, received_actor_context=None):
        calls["operate_args"] = (request, instance_ids, received_actor_context)
        return instance_ids

    def _ensure_target_organizations(organizations, received_actor_context):
        calls["target_org_args"] = (organizations, received_actor_context)

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
        FlowOnboardingService=types.SimpleNamespace(create_or_bind_asset=create_or_bind_asset),
    )
    _install_module(monkeypatch, "apps.monitor.services.manual_collect", ManualCollectService=object)
    _install_module(
        monkeypatch,
        "apps.monitor.views.monitor_instance",
        _build_actor_context=_build_actor_context,
        _ensure_operate_instances=_ensure_operate_instances,
        _ensure_target_organizations=_ensure_target_organizations,
    )
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)

    module = _load_module(
        "manual_collect_view_test_module",
        Path(__file__).resolve().parents[1] / "views" / "manual_collect.py",
    )

    request = types.SimpleNamespace(
        data={
            "instance_id": "inst-a",
            "monitor_object_id": 1,
            "protocol": "netflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Core Switch",
            "organizations": [7],
        }
    )

    response = module.ManualCollect().flow_asset(request)

    assert response == {"instance_id": "inst-a"}
    assert calls["operate_args"] == (request, ["inst-a"], actor_context)
    assert calls["target_org_args"] == ([7], actor_context)
    assert calls["create_or_bind_asset"] == request.data
