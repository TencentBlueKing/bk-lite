import importlib.util
import sys
import types
from pathlib import Path

import pytest
from django.http import QueryDict


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

    def lock_monitor_object(*, monitor_object_id, require_supported=True):
        calls["lock_monitor_object"] = {
            "monitor_object_id": monitor_object_id,
            "require_supported": require_supported,
        }

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
    assert calls["lock_monitor_object"] == {"monitor_object_id": 1, "require_supported": True}
    assert calls["operate_args"] == (request, ["inst-a"], actor_context)
    assert calls["target_org_args"] == ([7], actor_context)
    create_or_bind_call = dict(calls["create_or_bind_asset"])
    conflict_permission_checker = create_or_bind_call.pop("conflict_permission_checker")
    assert callable(conflict_permission_checker)
    assert create_or_bind_call == request.data


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

    def lock_monitor_object(*, monitor_object_id, require_supported=True):
        calls["lock_monitor_object"] = {
            "monitor_object_id": monitor_object_id,
            "require_supported": require_supported,
        }

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
    assert calls["lock_monitor_object"] == {"monitor_object_id": 1, "require_supported": True}
    assert calls["find_reusable_asset"] == {
        "monitor_object_id": 1,
        "cloud_region_id": 1,
        "ip": "10.0.0.12",
        "for_update": True,
    }
    assert calls["operate_args"] == (request, [existing_instance.id], actor_context)
    assert calls["target_org_args"] == ([7], actor_context)
    create_or_bind_call = dict(calls["create_or_bind_asset"])
    conflict_permission_checker = create_or_bind_call.pop("conflict_permission_checker")
    assert callable(conflict_permission_checker)
    assert create_or_bind_call == {
        **request.data,
        "instance_id": existing_instance.id,
        "allow_deleted_instance_reuse": True,
    }


def test_flow_asset_coerces_monitor_object_id_before_service_calls(monkeypatch, db):
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

    def lock_monitor_object(*, monitor_object_id, require_supported=True):
        calls["lock_monitor_object"] = {
            "monitor_object_id": monitor_object_id,
            "require_supported": require_supported,
        }

    def _build_actor_context(request):
        return actor_context

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
            find_reusable_asset=lambda **kwargs: None,
            lock_monitor_object=lock_monitor_object,
        ),
    )
    _install_module(monkeypatch, "apps.monitor.services.manual_collect", ManualCollectService=object)
    _install_module(
        monkeypatch,
        "apps.monitor.views.monitor_instance",
        _build_actor_context=_build_actor_context,
        _ensure_operate_instances=lambda request, instance_ids, received_actor_context=None: instance_ids,
        _ensure_target_organizations=lambda organizations, received_actor_context: None,
    )
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)

    module = _load_module(
        "manual_collect_view_test_module_monitor_object_id_coercion",
        Path(__file__).resolve().parents[1] / "views" / "manual_collect.py",
    )

    request = types.SimpleNamespace(
        data={
            "monitor_object_id": "1",
            "protocol": "netflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Core Switch",
            "organizations": [7],
        }
    )

    module.ManualCollect().flow_asset(request)

    assert calls["lock_monitor_object"] == {"monitor_object_id": 1, "require_supported": True}
    assert calls["create_or_bind_asset"]["monitor_object_id"] == 1
    assert callable(calls["create_or_bind_asset"]["conflict_permission_checker"])


@pytest.mark.parametrize(
    ("method_name", "module_name", "request_data", "expected_payload"),
    [
        (
            "flow_asset",
            "manual_collect_view_test_module_create_form_payload",
            {
                "monitor_object_id": "1",
                "protocol": "netflow",
                "cloud_region_id": "2",
                "ip": " 10.0.0.12 ",
                "name": "  Core Switch  ",
                "organizations": ["7", "8"],
                "fallback_sampling_rate": 3000,
            },
            {
                "monitor_object_id": 1,
                "protocol": "netflow",
                "cloud_region_id": 2,
                "ip": "10.0.0.12",
                "name": "Core Switch",
                "organizations": [7, 8],
                "fallback_sampling_rate": 3000,
            },
        ),
        (
            "update_flow_asset",
            "manual_collect_view_test_module_update_form_payload",
            {
                "instance_id": "inst-a",
                "name": "  Core Switch Updated  ",
                "cloud_region_id": "3",
                "ip": "10.0.0.13",
                "organizations": ["9"],
            },
            {
                "instance_id": "inst-a",
                "name": "Core Switch Updated",
                "cloud_region_id": 3,
                "ip": "10.0.0.13",
                "organizations": [9],
            },
        ),
    ],
)
def test_flow_asset_endpoints_normalize_querydict_payloads(monkeypatch, db, method_name, module_name, request_data, expected_payload):
    calls = {}
    actor_context = {"current_team": 7}

    class ViewSet:
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def create_or_bind_asset(**kwargs):
        calls["service_payload"] = kwargs
        return {"instance_id": kwargs.get("instance_id", "created-instance")}

    def update_asset(**kwargs):
        calls["service_payload"] = kwargs
        return {"instance_id": kwargs["instance_id"]}

    def lock_monitor_object(*, monitor_object_id, require_supported=True):
        calls["lock_monitor_object"] = {
            "monitor_object_id": monitor_object_id,
            "require_supported": require_supported,
        }

    def validate_instance_id(*, instance_id):
        calls.setdefault("validated_instance_ids", []).append(instance_id)
        return instance_id

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
            update_asset=update_asset,
            find_reusable_asset=lambda **kwargs: None,
            lock_monitor_object=lock_monitor_object,
            validate_instance_id=validate_instance_id,
        ),
    )
    _install_module(monkeypatch, "apps.monitor.services.manual_collect", ManualCollectService=object)
    _install_module(
        monkeypatch,
        "apps.monitor.views.monitor_instance",
        _build_actor_context=lambda request: actor_context,
        _ensure_operate_instances=lambda request, instance_ids, received_actor_context=None: instance_ids,
        _ensure_target_organizations=lambda organizations, received_actor_context: None,
    )
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)

    module = _load_module(
        module_name,
        Path(__file__).resolve().parents[1] / "views" / "manual_collect.py",
    )

    payload = QueryDict("", mutable=True)
    for field, value in request_data.items():
        if isinstance(value, list):
            payload.setlist(field, value)
        else:
            payload[field] = str(value)

    response = getattr(module.ManualCollect(), method_name)(types.SimpleNamespace(data=payload))

    assert response["instance_id"] == expected_payload.get("instance_id", "created-instance")
    service_payload = dict(calls["service_payload"])
    conflict_permission_checker = service_payload.pop("conflict_permission_checker", None)
    if method_name == "flow_asset":
        assert callable(conflict_permission_checker)
        assert calls["lock_monitor_object"] == {"monitor_object_id": 1, "require_supported": True}
    else:
        assert conflict_permission_checker is not None and callable(conflict_permission_checker)
        assert calls["validated_instance_ids"] == ["inst-a"]
    assert service_payload == expected_payload


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


def test_flow_asset_api_rejects_explicit_binding_for_unsupported_monitor_object(api_client, monkeypatch, db):
    from apps.monitor.models import MonitorInstance, MonitorObject
    from apps.monitor.views import manual_collect as manual_collect_view

    host_object = MonitorObject.objects.create(name="Host", display_name="Host")
    instance = MonitorInstance.objects.create(
        id="('host-device-1',)",
        name="Existing Host",
        monitor_object_id=host_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )

    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_target_organizations",
        lambda organizations, actor_context: None,
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": host_object.id,
            "instance_id": instance.id,
            "protocol": "sflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Existing Host",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Unsupported flow monitor object"

    instance.refresh_from_db()
    assert instance.enabled_protocols == ["netflow"]


def test_flow_asset_api_rejects_unknown_request_fields(api_client, monkeypatch):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService
    from apps.monitor.views import manual_collect as manual_collect_view

    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_target_organizations",
        lambda organizations, actor_context: None,
    )
    monkeypatch.setattr(FlowOnboardingService, "lock_monitor_object", lambda **kwargs: None)
    monkeypatch.setattr(FlowOnboardingService, "find_reusable_asset", lambda **kwargs: None)

    def fail_if_called(
        *,
        monitor_object_id,
        protocol,
        cloud_region_id,
        ip,
        name,
        organizations=None,
        instance_id=None,
        allow_deleted_instance_reuse=False,
        fallback_sampling_rate=None,
        conflict_permission_checker=None,
    ):
        raise AssertionError("create_or_bind_asset should not be called for invalid payloads")

    monkeypatch.setattr(FlowOnboardingService, "create_or_bind_asset", fail_if_called)

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": 1,
            "protocol": "netflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Core Switch",
            "unexpected_field": "boom",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Unknown request fields: unexpected_field"


def test_update_flow_asset_api_rejects_unknown_request_fields(api_client, monkeypatch):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService
    from apps.monitor.views import manual_collect as manual_collect_view

    monkeypatch.setattr(manual_collect_view, "_ensure_operate_instances", lambda request, instance_ids, actor_context=None: instance_ids)
    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_target_organizations",
        lambda organizations, actor_context: None,
    )

    def fail_if_called(
        *,
        instance_id,
        name=None,
        organizations=None,
        cloud_region_id=None,
        ip=None,
        fallback_sampling_rate=None,
        conflict_permission_checker=None,
    ):
        raise AssertionError("update_asset should not be called for invalid payloads")

    monkeypatch.setattr(FlowOnboardingService, "update_asset", fail_if_called)

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/update/",
        data={
            "instance_id": "inst-a",
            "name": "Core Switch",
            "unexpected_field": "boom",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Unknown request fields: unexpected_field"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/monitor/api/manual_collect/flow_asset/", []),
        ("/api/v1/monitor/api/manual_collect/flow_asset/", "boom"),
        ("/api/v1/monitor/api/manual_collect/flow_asset/update/", []),
        ("/api/v1/monitor/api/manual_collect/flow_asset/update/", "boom"),
    ],
)
def test_flow_asset_endpoints_reject_non_object_payloads(api_client, monkeypatch, path, payload):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService
    from apps.monitor.views import manual_collect as manual_collect_view

    monkeypatch.setattr(
        FlowOnboardingService,
        "lock_monitor_object",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("lock_monitor_object should not be called for invalid payloads")),
    )
    monkeypatch.setattr(
        FlowOnboardingService,
        "create_or_bind_asset",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("create_or_bind_asset should not be called for invalid payloads")),
    )
    monkeypatch.setattr(
        FlowOnboardingService,
        "update_asset",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("update_asset should not be called for invalid payloads")),
    )
    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: (_ for _ in ()).throw(
            AssertionError("_ensure_operate_instances should not be called for invalid payloads")
        ),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(path, data=payload, format="json")

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Request body must be an object"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("cloud_region_id", None, "Field cloud_region_id cannot be empty"),
        ("ip", "", "Field ip cannot be empty"),
    ],
)
def test_flow_asset_api_rejects_empty_identity_values(api_client, monkeypatch, field, value, message):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService

    monkeypatch.setattr(
        FlowOnboardingService,
        "lock_monitor_object",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("lock_monitor_object should not be called for invalid payloads")),
    )

    payload = {
        "monitor_object_id": 1,
        "protocol": "netflow",
        "cloud_region_id": 1,
        "ip": "10.0.0.12",
        "name": "Core Switch",
    }
    payload[field] = value

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data=payload,
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == message


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/",
            {
                "monitor_object_id": 1,
                "protocol": "netflow",
                "cloud_region_id": "",
                "ip": "10.0.0.12",
                "name": "Core Switch",
            },
        ),
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/update/",
            {
                "instance_id": "inst-a",
                "cloud_region_id": "not-an-int",
            },
        ),
    ],
)
def test_flow_asset_endpoints_reject_invalid_cloud_region_id_values(api_client, monkeypatch, path, payload):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService
    from apps.monitor.views import manual_collect as manual_collect_view

    monkeypatch.setattr(
        FlowOnboardingService,
        "lock_monitor_object",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("lock_monitor_object should not be called for invalid payloads")),
    )
    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: (_ for _ in ()).throw(
            AssertionError("_ensure_operate_instances should not be called for invalid payloads")
        ),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(path, data=payload, format="json")

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Field cloud_region_id must be an integer"


def test_flow_asset_api_rejects_invalid_monitor_object_id_values(api_client, monkeypatch):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService

    monkeypatch.setattr(
        FlowOnboardingService,
        "lock_monitor_object",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("lock_monitor_object should not be called for invalid payloads")),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": "abc",
            "protocol": "netflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Core Switch",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Field monitor_object_id must be an integer"


def test_flow_asset_organizations_validator_normalizes_tuple_values():
    from apps.monitor.views import manual_collect as manual_collect_view

    assert manual_collect_view._validate_organizations("organizations", ("1", 2, " 2 ", "1")) == [1, 2]


@pytest.mark.parametrize(
    ("path", "payload", "downstream_attr"),
    [
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/",
            {
                "monitor_object_id": 1,
                "protocol": "netflow",
                "cloud_region_id": 1,
                "ip": "10.0.0.12",
                "name": "Core Switch",
                "organizations": "1,2",
            },
            "lock_monitor_object",
        ),
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/update/",
            {
                "instance_id": "inst-a",
                "organizations": [1, "bad-org"],
            },
            "update_asset",
        ),
    ],
)
def test_flow_asset_endpoints_reject_invalid_organizations_payloads(api_client, monkeypatch, path, payload, downstream_attr):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService
    from apps.monitor.views import manual_collect as manual_collect_view

    monkeypatch.setattr(
        FlowOnboardingService,
        downstream_attr,
        lambda **kwargs: (_ for _ in ()).throw(AssertionError(f"{downstream_attr} should not be called for invalid payloads")),
    )
    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: (_ for _ in ()).throw(
            AssertionError("_ensure_operate_instances should not be called for invalid payloads")
        ),
    )
    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_target_organizations",
        lambda organizations, actor_context: (_ for _ in ()).throw(
            AssertionError("_ensure_target_organizations should not be called for invalid payloads")
        ),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(path, data=payload, format="json")

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Field organizations must be a list or tuple of integers"


def test_flow_asset_api_rejects_unsupported_protocol(api_client, monkeypatch):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService

    monkeypatch.setattr(
        FlowOnboardingService,
        "lock_monitor_object",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("lock_monitor_object should not be called for invalid payloads")),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": 1,
            "protocol": "ipfix",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Core Switch",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Field protocol must be a supported flow protocol"


def test_flow_asset_api_rejects_unsupported_monitor_object(api_client, monkeypatch, db):
    from apps.monitor.models import MonitorObject
    from apps.monitor.services.flow_onboarding import FlowOnboardingService

    unsupported_object = MonitorObject.objects.create(name="Host", display_name="Host")

    monkeypatch.setattr(
        FlowOnboardingService,
        "create_or_bind_asset",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("create_or_bind_asset should not be called")),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": unsupported_object.id,
            "protocol": "netflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Core Host",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Unsupported flow monitor object"


def test_flow_asset_api_rejects_nonexistent_monitor_object(api_client, monkeypatch):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService

    monkeypatch.setattr(
        FlowOnboardingService,
        "create_or_bind_asset",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("create_or_bind_asset should not be called")),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": 999999,
            "protocol": "netflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Missing Object",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Monitor object does not exist"


def test_flow_asset_api_rejects_duplicate_tuple_as_validation_error(api_client, monkeypatch, db):
    from apps.monitor.models import MonitorInstance, MonitorObject
    from apps.monitor.views import manual_collect as manual_collect_view

    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    MonitorObject.objects.create(name="Router", display_name="Router")
    MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )

    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: instance_ids,
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": switch_object.id + 1,
            "protocol": "sflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Core Router",
            "organizations": [1],
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Flow asset already exists"
    assert not MonitorInstance.objects.filter(
        monitor_object_id=switch_object.id + 1,
        cloud_region_id=1,
        ip="10.0.0.12",
    ).exists()


def test_flow_asset_api_checks_operate_permission_before_cross_object_duplicate_error(api_client, monkeypatch, db):
    from apps.core.exceptions.base_app_exception import UnauthorizedException
    from apps.monitor.models import MonitorInstance, MonitorObject
    from apps.monitor.views import manual_collect as manual_collect_view

    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    router_object = MonitorObject.objects.create(name="Router", display_name="Router")
    conflicting = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Router",
        monitor_object_id=router_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )
    operate_calls = []

    def fake_ensure_operate_instances(request, instance_ids, actor_context=None):
        normalized_ids = list(instance_ids)
        operate_calls.append(normalized_ids)
        if normalized_ids == [conflicting.id]:
            raise UnauthorizedException("无权限操作指定监控实例")
        return normalized_ids

    monkeypatch.setattr(manual_collect_view, "_ensure_operate_instances", fake_ensure_operate_instances)
    monkeypatch.setattr(manual_collect_view, "_ensure_target_organizations", lambda organizations, actor_context: None)

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": switch_object.id,
            "protocol": "sflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Core Switch",
            "organizations": [1],
        },
        format="json",
    )

    assert response.status_code == 401, response.content
    assert response.json()["message"] == "无权限操作指定监控实例"
    assert operate_calls == [[conflicting.id]]
    assert not MonitorInstance.objects.filter(
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
    ).exists()


def test_flow_asset_api_rejects_duplicate_name_on_restore_as_validation_error(api_client, monkeypatch, db):
    from apps.monitor.models import MonitorInstance, MonitorObject
    from apps.monitor.views import manual_collect as manual_collect_view

    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    created = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
        is_deleted=True,
    )
    MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=2,
        ip="10.0.0.13",
        fallback_sampling_rate=1000,
        enabled_protocols=["sflow"],
    )

    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: instance_ids,
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
            "organizations": [1],
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "实例名称已存在"
    created.refresh_from_db()
    assert created.is_deleted is True


def test_flow_asset_api_rejects_nonexistent_instance_id(api_client, monkeypatch, db):
    from apps.monitor.models import MonitorObject
    from apps.monitor.services.flow_onboarding import FlowOnboardingService
    from apps.monitor.views import manual_collect as manual_collect_view

    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: (_ for _ in ()).throw(
            AssertionError("_ensure_operate_instances should not be called for invalid payloads")
        ),
    )
    monkeypatch.setattr(
        FlowOnboardingService,
        "create_or_bind_asset",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("create_or_bind_asset should not be called")),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": switch_object.id,
            "instance_id": "missing-instance",
            "protocol": "netflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Missing Instance",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Monitor instance does not exist"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/",
            {
                "monitor_object_id": 1,
                "protocol": "netflow",
                "cloud_region_id": 1,
                "ip": "10.0.0.12",
                "name": "Core Switch",
                "fallback_sampling_rate": "invalid",
            },
        ),
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/update/",
            {
                "instance_id": "inst-a",
                "fallback_sampling_rate": -1,
            },
        ),
    ],
)
def test_flow_asset_endpoints_reject_invalid_fallback_sampling_rate(api_client, monkeypatch, path, payload):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService
    from apps.monitor.views import manual_collect as manual_collect_view

    monkeypatch.setattr(
        FlowOnboardingService,
        "lock_monitor_object",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("lock_monitor_object should not be called for invalid payloads")),
    )
    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: (_ for _ in ()).throw(
            AssertionError("_ensure_operate_instances should not be called for invalid payloads")
        ),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(path, data=payload, format="json")

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Field fallback_sampling_rate must be a non-negative integer"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/",
            {
                "monitor_object_id": 1,
                "protocol": "netflow",
                "cloud_region_id": 1,
                "ip": " not-an-ip ",
                "name": "Core Switch",
            },
        ),
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/update/",
            {
                "instance_id": "inst-a",
                "ip": "999.999.999.999",
            },
        ),
    ],
)
def test_flow_asset_endpoints_reject_invalid_ip_values(api_client, monkeypatch, path, payload):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService
    from apps.monitor.views import manual_collect as manual_collect_view

    monkeypatch.setattr(
        FlowOnboardingService,
        "lock_monitor_object",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("lock_monitor_object should not be called for invalid payloads")),
    )
    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: (_ for _ in ()).throw(
            AssertionError("_ensure_operate_instances should not be called for invalid payloads")
        ),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(path, data=payload, format="json")

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Field ip must be a valid IP address"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("cloud_region_id", None, "Field cloud_region_id cannot be empty"),
        ("ip", "", "Field ip cannot be empty"),
    ],
)
def test_update_flow_asset_api_rejects_empty_identity_values(api_client, monkeypatch, field, value, message):
    from apps.monitor.views import manual_collect as manual_collect_view

    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: (_ for _ in ()).throw(
            AssertionError("_ensure_operate_instances should not be called for invalid payloads")
        ),
    )

    payload = {
        "instance_id": "inst-a",
        "cloud_region_id": 1,
        "ip": "10.0.0.12",
    }
    payload[field] = value

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/update/",
        data=payload,
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == message


def test_update_flow_asset_api_rejects_enabled_protocols_field(api_client, monkeypatch):
    from apps.monitor.views import manual_collect as manual_collect_view

    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: (_ for _ in ()).throw(
            AssertionError("_ensure_operate_instances should not be called for invalid payloads")
        ),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/update/",
        data={
            "instance_id": "inst-a",
            "enabled_protocols": ["netflow"],
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Unknown request fields: enabled_protocols"


def test_update_flow_asset_api_rejects_nonexistent_instance_id(api_client, monkeypatch):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService
    from apps.monitor.views import manual_collect as manual_collect_view

    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: (_ for _ in ()).throw(
            AssertionError("_ensure_operate_instances should not be called for invalid payloads")
        ),
    )
    monkeypatch.setattr(
        FlowOnboardingService,
        "update_asset",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("update_asset should not be called")),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/update/",
        data={
            "instance_id": "missing-instance",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "Monitor instance does not exist"


def test_update_flow_asset_api_rejects_duplicate_name_as_validation_error(api_client, monkeypatch, db):
    from apps.monitor.models import MonitorInstance, MonitorObject
    from apps.monitor.views import manual_collect as manual_collect_view

    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Flow Asset A",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )
    target = MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Flow Asset B",
        monitor_object_id=switch_object.id,
        cloud_region_id=2,
        ip="10.0.0.13",
        fallback_sampling_rate=2000,
        enabled_protocols=["sflow"],
    )

    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: instance_ids,
    )
    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_target_organizations",
        lambda organizations, actor_context: None,
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/update/",
        data={
            "instance_id": target.id,
            "name": "Flow Asset A",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert response.json()["message"] == "实例名称已存在"
    target.refresh_from_db()
    assert target.name == "Flow Asset B"


@pytest.mark.parametrize(
    ("path", "payload", "message"),
    [
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/",
            {
                "monitor_object_id": 1,
                "protocol": "netflow",
                "cloud_region_id": 1,
                "ip": "10.0.0.12",
                "name": "",
            },
            "Field name cannot be empty",
        ),
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/",
            {
                "monitor_object_id": 1,
                "protocol": "netflow",
                "cloud_region_id": 1,
                "ip": "10.0.0.12",
                "name": "   ",
            },
            "Field name cannot be empty",
        ),
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/",
            {
                "monitor_object_id": 1,
                "protocol": "netflow",
                "cloud_region_id": 1,
                "ip": "10.0.0.12",
                "name": 123,
            },
            "Field name must be a string",
        ),
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/update/",
            {
                "instance_id": "inst-a",
                "name": "",
            },
            "Field name cannot be empty",
        ),
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/update/",
            {
                "instance_id": "inst-a",
                "name": "   ",
            },
            "Field name cannot be empty",
        ),
        (
            "/api/v1/monitor/api/manual_collect/flow_asset/update/",
            {
                "instance_id": "inst-a",
                "name": 123,
            },
            "Field name must be a string",
        ),
    ],
)
def test_flow_asset_endpoints_reject_invalid_name_values(api_client, monkeypatch, path, payload, message):
    from apps.monitor.services.flow_onboarding import FlowOnboardingService
    from apps.monitor.views import manual_collect as manual_collect_view

    monkeypatch.setattr(
        FlowOnboardingService,
        "lock_monitor_object",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("lock_monitor_object should not be called for invalid payloads")),
    )
    monkeypatch.setattr(
        FlowOnboardingService,
        "create_or_bind_asset",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("create_or_bind_asset should not be called for invalid payloads")),
    )
    monkeypatch.setattr(
        FlowOnboardingService,
        "update_asset",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("update_asset should not be called for invalid payloads")),
    )
    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: (_ for _ in ()).throw(
            AssertionError("_ensure_operate_instances should not be called for invalid payloads")
        ),
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(path, data=payload, format="json")

    assert response.status_code == 400, response.content
    assert response.json()["message"] == message


def test_update_flow_asset_api_checks_operate_permission_before_cross_object_duplicate_error(api_client, monkeypatch, db):
    from apps.core.exceptions.base_app_exception import UnauthorizedException
    from apps.monitor.models import MonitorInstance, MonitorObject
    from apps.monitor.views import manual_collect as manual_collect_view

    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    router_object = MonitorObject.objects.create(name="Router", display_name="Router")
    target = MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=2,
        ip="10.0.0.13",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )
    conflicting = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Router",
        monitor_object_id=router_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["sflow"],
    )
    operate_calls = []

    def fake_ensure_operate_instances(request, instance_ids, actor_context=None):
        normalized_ids = list(instance_ids)
        operate_calls.append(normalized_ids)
        if normalized_ids == [conflicting.id]:
            raise UnauthorizedException("无权限操作指定监控实例")
        return normalized_ids

    monkeypatch.setattr(manual_collect_view, "_ensure_operate_instances", fake_ensure_operate_instances)
    monkeypatch.setattr(manual_collect_view, "_ensure_target_organizations", lambda organizations, actor_context: None)

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/update/",
        data={
            "instance_id": target.id,
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
        },
        format="json",
    )

    assert response.status_code == 401, response.content
    assert response.json()["message"] == "无权限操作指定监控实例"
    assert operate_calls == [[target.id], [conflicting.id]]
    target.refresh_from_db()
    assert target.cloud_region_id == 2
    assert target.ip == "10.0.0.13"


def test_flow_asset_api_normalizes_ip_for_creation_and_reuse(api_client, monkeypatch, db):
    from apps.monitor.models import MonitorInstance, MonitorObject
    from apps.monitor.views import manual_collect as manual_collect_view

    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    monkeypatch.setattr(
        manual_collect_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: instance_ids,
    )

    api_client.cookies["current_team"] = "1"
    create_response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": switch_object.id,
            "protocol": "netflow",
            "cloud_region_id": 1,
            "ip": " 10.0.0.12 ",
            "name": "Core Switch",
            "organizations": [1],
        },
        format="json",
    )

    assert create_response.status_code == 200, create_response.content
    created_instance_id = create_response.json()["data"]["instance_id"]
    created_instance = MonitorInstance.objects.get(id=created_instance_id)
    assert f"flow:{switch_object.id}:1:10.0.0.12" in created_instance.id
    assert " 10.0.0.12 " not in created_instance.id
    assert created_instance.ip == "10.0.0.12"
    assert created_instance.enabled_protocols == ["netflow"]

    reuse_response = api_client.post(
        "/api/v1/monitor/api/manual_collect/flow_asset/",
        data={
            "monitor_object_id": switch_object.id,
            "protocol": "sflow",
            "cloud_region_id": 1,
            "ip": "10.0.0.12",
            "name": "Core Switch",
            "organizations": [1],
        },
        format="json",
    )

    assert reuse_response.status_code == 200, reuse_response.content
    assert reuse_response.json()["data"]["instance_id"] == created_instance_id

    created_instance.refresh_from_db()
    assert set(created_instance.enabled_protocols) == {"netflow", "sflow"}
    assert MonitorInstance.objects.filter(
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
    ).count() == 1
