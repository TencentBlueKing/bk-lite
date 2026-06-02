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


def test_flow_asset_checks_operate_permission_before_binding_instance(monkeypatch, db):
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

    def lock_monitor_object(*, monitor_object_id):
        calls["lock_monitor_object"] = monitor_object_id

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
        FlowOnboardingService=types.SimpleNamespace(
            create_or_bind_asset=create_or_bind_asset,
            lock_monitor_object=lock_monitor_object,
        ),
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
    assert calls["lock_monitor_object"] == 1
    assert calls["operate_args"] == (request, ["inst-a"], actor_context)
    assert calls["target_org_args"] == ([7], actor_context)
    assert calls["create_or_bind_asset"] == request.data


def test_flow_asset_checks_operate_permission_before_reusing_existing_instance(monkeypatch, db):
    calls = {}
    actor_context = {"current_team": 7}
    existing_instance = types.SimpleNamespace(id="inst-reused", is_deleted=True)

    class ViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def create_or_bind_asset(**kwargs):
        calls["create_or_bind_asset"] = kwargs
        return {"instance_id": existing_instance.id}

    def lock_monitor_object(*, monitor_object_id):
        calls["lock_monitor_object"] = monitor_object_id

    def find_reusable_asset(*, monitor_object_id, cloud_region_id, ip, for_update=False):
        calls["find_reusable_asset"] = {
            "monitor_object_id": monitor_object_id,
            "cloud_region_id": cloud_region_id,
            "ip": ip,
            "for_update": for_update,
        }
        return existing_instance

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
        FlowOnboardingService=types.SimpleNamespace(
            create_or_bind_asset=create_or_bind_asset,
            find_reusable_asset=find_reusable_asset,
            lock_monitor_object=lock_monitor_object,
        ),
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
        "manual_collect_view_test_module_reused",
        Path(__file__).resolve().parents[1] / "views" / "manual_collect.py",
    )

    request = types.SimpleNamespace(
        data={
            "monitor_object_id": 1,
            "protocol": "sflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Core Switch",
            "organizations": [7],
        }
    )

    response = module.ManualCollect().flow_asset(request)

    assert response == {"instance_id": existing_instance.id}
    assert calls["lock_monitor_object"] == 1
    assert calls["find_reusable_asset"] == {
        "monitor_object_id": 1,
        "cloud_region_id": 1,
        "ip": "10.0.0.12",
        "for_update": True,
    }
    assert calls["operate_args"] == (request, [existing_instance.id], actor_context)
    assert calls["target_org_args"] == ([7], actor_context)
    assert calls["create_or_bind_asset"] == {
        **request.data,
        "instance_id": existing_instance.id,
        "allow_deleted_instance_reuse": True,
    }


def test_flow_asset_api_restores_soft_deleted_reused_instance(api_client, monkeypatch, db):
    from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObject
    from apps.monitor.services.manual_collect import ManualCollectService
    from apps.monitor.views import manual_collect as manual_collect_view

    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    deleted_instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
        is_deleted=True,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance_id=deleted_instance.id, organization=1)

    operate_calls = []
    target_org_calls = []
    restored_rule_calls = []

    def fake_ensure_operate_instances(request, instance_ids, actor_context=None):
        operate_calls.append((list(instance_ids), actor_context["current_team"]))
        return instance_ids

    def fake_ensure_target_organizations(organizations, actor_context):
        target_org_calls.append((list(organizations), actor_context["current_team"]))

    monkeypatch.setattr(manual_collect_view, "_ensure_operate_instances", fake_ensure_operate_instances)
    monkeypatch.setattr(manual_collect_view, "_ensure_target_organizations", fake_ensure_target_organizations)
    monkeypatch.setattr(
        ManualCollectService,
        "create_organization_rule_by_child_object",
        lambda monitor_object_id, instance_id, organization_ids: restored_rule_calls.append(
            (monitor_object_id, instance_id, list(organization_ids))
        ),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": switch_object.id,
            "protocol": "sflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Core Switch",
            "organizations": [2],
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["data"] == {
        "instance_id": deleted_instance.id,
        "enabled_protocols": ["netflow", "sflow"],
    }

    deleted_instance.refresh_from_db()
    assert deleted_instance.is_deleted is False
    assert deleted_instance.cloud_region_id == 1
    assert deleted_instance.ip == "10.0.0.12"
    assert set(deleted_instance.enabled_protocols) == {"netflow", "sflow"}
    assert set(
        MonitorInstanceOrganization.objects.filter(monitor_instance_id=deleted_instance.id).values_list("organization", flat=True)
    ) == {2}
    assert operate_calls == [([deleted_instance.id], 1)]
    assert target_org_calls == [([2], 1)]
    assert restored_rule_calls == [(switch_object.id, deleted_instance.id, [2])]
