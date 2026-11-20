"""环境安装公开服务契约：授权隔离和同请求重试。"""
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.node_mgmt.models import CloudRegion, PackageVersion
from apps.node_mgmt.services.environment_install import EnvironmentInstallService

pytestmark = pytest.mark.django_db


def test_long_owner_is_stored_on_the_grant_and_truncated_on_the_token():
    region = CloudRegion.objects.create(name="environment-long-owner")
    package = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="x86_64",
        object="Controller",
        version="test-v1",
        name="test.tar.gz",
        sha256="c" * 64,
    )
    owner = "u" * 100
    grant, _ = EnvironmentInstallService.create(
        owner=owner,
        domain="test",
        team=1,
        cloud_region_id=region.pk,
        package_id=package.pk,
        expires_at=timezone.now() + timedelta(hours=1),
        max_nodes=1,
    )
    assert grant.owner == owner
    assert grant.token.created_by == owner[:32]
    assert len(grant.token.created_by) <= 32


def test_environment_request_retry_keeps_node_and_consumes_one_slot():
    region = CloudRegion.objects.create(name="environment-test")
    package = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture="x86_64",
        object="Controller",
        version="test-v1",
        name="test.tar.gz",
        sha256="a" * 64,
    )
    grant, key = EnvironmentInstallService.create(
        owner="installer",
        domain="test",
        team=1,
        cloud_region_id=region.pk,
        package_id=package.pk,
        expires_at=timezone.now() + timedelta(hours=1),
        max_nodes=1,
    )
    request = dict(
        grant_id=str(grant.pk),
        installation_key=key,
        request_id=str(uuid4()),
        node_id=str(uuid4()),
        ip="192.0.2.10",
        node_name="host-a",
        os="linux",
        cpu_architecture="x86_64",
        team=[1],
        user_info={"user": "installer", "domain": "test"},
    )
    first = EnvironmentInstallService.reserve(**request)
    retry = EnvironmentInstallService.reserve(**request)
    assert first["install_id"] == retry["install_id"]
    assert first["node_id"] == request["node_id"]
    assert first["status"] == "pending"
    with pytest.raises(ValueError, match="quota"):
        EnvironmentInstallService.reserve(**{**request, "request_id": str(uuid4()), "node_id": str(uuid4()), "ip": "192.0.2.11"})


@pytest.fixture
def environment_request():
    region = CloudRegion.objects.create(name="environment-scope")
    package = PackageVersion.objects.create(
        type="controller", os="linux", cpu_architecture="x86_64", object="Controller", version="scope-v1", name="scope.tar.gz", sha256="b" * 64
    )
    grant, key = EnvironmentInstallService.create(
        owner="installer",
        domain="test",
        team=1,
        cloud_region_id=region.pk,
        package_id=package.pk,
        expires_at=timezone.now() + timedelta(hours=1),
        max_nodes=2,
    )
    return grant, dict(
        grant_id=str(grant.pk),
        installation_key=key,
        request_id=str(uuid4()),
        node_id=str(uuid4()),
        ip="192.0.2.20",
        node_name="host-b",
        os="linux",
        cpu_architecture="x86_64",
        team=[1],
        user_info={"user": "installer", "domain": "test"},
    )


def test_status_cannot_be_read_by_another_organization(environment_request):
    grant, request = environment_request
    attempt = EnvironmentInstallService.reserve(**request)
    identity = {k: request[k] for k in ("grant_id", "installation_key", "team", "user_info")}
    result = EnvironmentInstallService.status(**identity, install_id=attempt["install_id"])
    assert result["status"] == "pending"
    with pytest.raises(PermissionError):
        EnvironmentInstallService.status(**{**identity, "team": [2]}, install_id=attempt["install_id"])


def test_revoked_grant_cannot_register_pending_node(environment_request):
    grant, request = environment_request
    EnvironmentInstallService.reserve(**request)
    grant.token.enabled = False
    grant.token.save(update_fields=["enabled"])
    with pytest.raises(PermissionError):
        EnvironmentInstallService.validate_registration(
            request["node_id"], {"ip": request["ip"], "tags": ["zone:%s" % grant.cloud_region_id, "group:1"]}
        )


def test_gateway_status_enforces_grant_organization_and_scope(environment_request, settings):
    import json

    from django.test import RequestFactory

    from apps.core.openapi.testing import acting_headers, create_system_tenant
    from apps.core.openapi.views import invoke_view
    from apps.node_mgmt import openapi_api  # noqa: F401

    settings.OPENAPI_INVOKE_TIMEOUT = 0
    grant, request = environment_request
    user, key = create_system_tenant(1, username="installer", plaintext_token=request["installation_key"])
    grant.domain = user.domain
    grant.save(update_fields=["domain"])
    request["user_info"]["domain"] = user.domain
    attempt = EnvironmentInstallService.reserve(**request)
    payload = {"grant_id": str(grant.pk), "installation_key": key, "install_id": attempt["install_id"]}
    factory = RequestFactory()
    url = "/openapi/v1/node-mgmt/environment-install-status"
    response = invoke_view(
        factory.post(url, data=json.dumps(payload), content_type="application/json", **acting_headers(key, user, 1)),
        "node-mgmt",
        "environment-install-status",
    )
    assert response.status_code == 200
    assert json.loads(response.content)["data"]["node_id"] == request["node_id"]
    other_user, _ = create_system_tenant(2, username="other-installer", plaintext_token=key)
    denied = invoke_view(
        factory.post(url, data=json.dumps(payload), content_type="application/json", **acting_headers(key, other_user, 2)),
        "node-mgmt",
        "environment-install-status",
    )
    assert denied.status_code == 403


def test_request_returns_structured_session_bound_to_reserved_identity(environment_request, settings):
    from apps.node_mgmt.models import SidecarEnv
    from apps.node_mgmt.services.install_token import InstallTokenService

    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "environment-install"}}
    grant, request = environment_request
    SidecarEnv.objects.create(cloud_region=grant.cloud_region, key="NODE_SERVER_URL", value="https://platform.example")
    result = EnvironmentInstallService.request(**request)
    assert result["config_url"].startswith("https://platform.example/api/v1/node_mgmt/open_api/installer/session?token=")
    token = result["config_url"].split("token=", 1)[1]
    session = InstallTokenService.inspect_token_data(token)
    assert session["node_id"] == request["node_id"]
    assert session["organizations"] == [1]
    assert session["package_id"] == grant.package_id
    assert result["package_sha256"] == "b" * 64


def test_sidecar_first_heartbeat_rejects_forged_organization(environment_request, monkeypatch):
    from types import SimpleNamespace

    from apps.core.exceptions.base_app_exception import UnauthorizedException
    from apps.node_mgmt.services.sidecar import Sidecar

    grant, request = environment_request
    EnvironmentInstallService.reserve(**request)
    heartbeat = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "host-b",
            "node_details": {
                "ip": request["ip"],
                "operating_system": "Linux",
                "cpu_architecture": "x86_64",
                "collector_configuration_directory": "/opt/fusion-collectors/generated",
                "metrics": {},
                "status": {"status": 0},
                "log_file_list": [],
                "tags": [f"zone:{grant.cloud_region_id}", "group:2"],
            },
        },
    )
    with pytest.raises(UnauthorizedException):
        Sidecar.update_node_client(heartbeat, request["node_id"])


@pytest.mark.parametrize(
    "changes",
    [
        {"team": [2]},
        {"user_info": {"user": "other", "domain": "test"}},
        {"installation_key": "bksys_" + "0" * 64},
    ],
)
def test_wrong_scope_or_key_cannot_reserve(environment_request, changes):
    _, request = environment_request
    with pytest.raises(PermissionError):
        EnvironmentInstallService.reserve(**{**request, **changes})


def test_conflicting_retry_cannot_reassign_identity(environment_request):
    _, request = environment_request
    EnvironmentInstallService.reserve(**request)
    with pytest.raises(ValueError, match="conflict"):
        EnvironmentInstallService.reserve(**{**request, "ip": "192.0.2.99"})


def test_first_heartbeat_registers_and_repeat_keeps_identity(environment_request, monkeypatch):
    from types import SimpleNamespace

    from apps.node_mgmt.services.sidecar import Sidecar

    grant, request = environment_request
    attempt = EnvironmentInstallService.reserve(**request)
    heartbeat = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "host-b",
            "node_details": {
                "ip": request["ip"],
                "operating_system": "Linux",
                "cpu_architecture": "x86_64",
                "collector_configuration_directory": "/opt/fusion-collectors/generated",
                "metrics": {},
                "status": {"status": 0},
                "log_file_list": [],
                "tags": [
                    f"zone:{grant.cloud_region_id}",
                    "group:1",
                    f"environment_install:{attempt['install_id']}",
                    f"environment_package_sha256:{grant.package_sha256}",
                ],
            },
        },
    )
    Sidecar.update_node_client(heartbeat, request["node_id"])
    identity = {k: request[k] for k in ("grant_id", "installation_key", "team", "user_info")}
    result = EnvironmentInstallService.status(**identity, install_id=attempt["install_id"])
    assert result["status"] == "registered"
    assert result["last_seen"] is not None
    again = EnvironmentInstallService.reserve(**request)
    assert again["install_id"] == attempt["install_id"]
    assert again["status"] == "registered"
    assert "config_url" not in EnvironmentInstallService.request(**request)
    # A concurrent first heartbeat may have missed the now-existing node before entering the region lock.
    existing_node, _, created = Sidecar._create_sidecar_node(
        request["node_id"],
        {
            "cloud_region_id": grant.cloud_region_id,
            "ip": request["ip"],
        },
    )
    assert existing_node.id == request["node_id"] and not created
    from apps.node_mgmt.models import EnvironmentInstallAttempt, Node

    EnvironmentInstallAttempt.objects.filter(pk=attempt["install_id"]).update(last_heartbeat_at=timezone.now() - timedelta(minutes=10))
    Node.objects.filter(pk=request["node_id"]).update(updated_at=timezone.now())
    assert EnvironmentInstallService.status(**identity, install_id=attempt["install_id"])["status"] == "pending"

    # Real Sidecar sends If-None-Match after its first successful heartbeat.
    from django.core.cache import cache

    original_cache_get = cache.get
    monkeypatch.setattr(
        cache,
        "get",
        lambda key, *args, **kwargs: "environment-etag" if key == f"node_etag_{request['node_id']}" else original_cache_get(key, *args, **kwargs),
    )
    heartbeat.headers["If-None-Match"] = '"environment-etag"'
    assert Sidecar.update_node_client(heartbeat, request["node_id"]).status_code == 304
    assert EnvironmentInstallService.status(**identity, install_id=attempt["install_id"])["status"] == "registered"
    # A cached response must still require the bound installation receipt.
    EnvironmentInstallAttempt.objects.filter(pk=attempt["install_id"]).update(last_heartbeat_at=timezone.now() - timedelta(minutes=10))
    heartbeat.data["node_details"]["tags"] = ["group:1"]
    assert Sidecar.update_node_client(heartbeat, request["node_id"]).status_code == 304
    assert EnvironmentInstallService.status(**identity, install_id=attempt["install_id"])["status"] == "pending"


def test_revoked_install_session_cannot_issue_runtime_credentials(environment_request):
    from apps.core.exceptions.base_app_exception import UnauthorizedException
    from apps.node_mgmt.services.installer_session import InstallerSessionService

    grant, request = environment_request
    EnvironmentInstallService.reserve(**request)
    grant.token.enabled = False
    grant.token.save(update_fields=["enabled"])
    with pytest.raises(UnauthorizedException):
        InstallerSessionService.build_session_config(
            "not-a-real-session",
            token_data={
                "node_id": request["node_id"],
                "ip": request["ip"],
                "user": "installer",
                "os": "linux",
                "cpu_architecture": "x86_64",
                "package_id": grant.package_id,
                "cloud_region_id": grant.cloud_region_id,
                "organizations": [1],
                "node_name": "host-b",
                "remaining_usage": 5,
                "environment_grant_id": str(grant.id),
            },
        )


def test_deleted_registered_node_cannot_be_silently_recreated(environment_request):
    from apps.node_mgmt.models import EnvironmentInstallAttempt

    _, request = environment_request
    result = EnvironmentInstallService.reserve(**request)
    EnvironmentInstallAttempt.objects.filter(pk=result["install_id"]).update(registered_at=timezone.now())
    with pytest.raises(PermissionError, match="already registered"):
        EnvironmentInstallService.validate_registration(request["node_id"], {"ip": request["ip"], "tags": []})


def test_status_requires_fresh_heartbeat_and_bound_organization(environment_request):
    from apps.node_mgmt.models import EnvironmentInstallAttempt, Node, NodeOrganization

    grant, request = environment_request
    result = EnvironmentInstallService.reserve(**request)
    EnvironmentInstallAttempt.objects.filter(pk=result["install_id"]).update(registered_at=timezone.now())
    node = Node.objects.create(
        id=request["node_id"],
        name=request["node_name"],
        ip=request["ip"],
        operating_system="linux",
        cloud_region=grant.cloud_region,
        collector_configuration_directory="/opt/fusion-collectors/generated",
    )
    identity = {k: request[k] for k in ("grant_id", "installation_key", "team", "user_info")}
    assert EnvironmentInstallService.status(**identity, install_id=result["install_id"])["status"] == "pending"
    NodeOrganization.objects.create(node=node, organization=grant.team)
    Node.objects.filter(pk=node.pk).update(updated_at=timezone.now() - timedelta(minutes=10))
    assert EnvironmentInstallService.status(**identity, install_id=result["install_id"])["status"] == "pending"


def test_gateway_request_enforces_grant_organization(environment_request, settings):
    import json

    from django.test import RequestFactory

    from apps.core.openapi.testing import acting_headers, create_system_tenant
    from apps.core.openapi.views import invoke_view
    from apps.node_mgmt import openapi_api  # noqa: F401
    from apps.node_mgmt.models import SidecarEnv

    settings.OPENAPI_INVOKE_TIMEOUT = 0
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "environment-gateway"}}
    grant, request = environment_request
    user, key = create_system_tenant(1, username="installer", plaintext_token=request["installation_key"])
    grant.domain = user.domain
    grant.save(update_fields=["domain"])
    SidecarEnv.objects.create(cloud_region=grant.cloud_region, key="NODE_SERVER_URL", value="https://platform.example")
    payload = {k: v for k, v in request.items() if k not in ("team", "user_info")}
    factory = RequestFactory()
    url = "/openapi/v1/node-mgmt/environment-install"
    response = invoke_view(
        factory.post(url, data=json.dumps(payload), content_type="application/json", **acting_headers(key, user, 1)),
        "node-mgmt",
        "environment-install",
    )
    assert response.status_code == 200
    other_user, _ = create_system_tenant(2, username="other-installer", plaintext_token=key)
    payload.update(request_id=str(uuid4()), node_id=str(uuid4()), ip="192.0.2.21")
    denied = invoke_view(
        factory.post(url, data=json.dumps(payload), content_type="application/json", **acting_headers(key, other_user, 2)),
        "node-mgmt",
        "environment-install",
    )
    assert denied.status_code == 403
    assert grant.attempts.count() == 1


def test_two_grants_cannot_reserve_same_region_address(environment_request):
    grant, request = environment_request
    EnvironmentInstallService.reserve(**request)
    other, key = EnvironmentInstallService.create(
        owner=grant.owner,
        domain=grant.domain,
        team=grant.team,
        cloud_region_id=grant.cloud_region_id,
        package_id=grant.package_id,
        expires_at=timezone.now() + timedelta(hours=1),
        max_nodes=2,
    )
    with pytest.raises(ValueError, match="address conflict"):
        EnvironmentInstallService.reserve(
            **{**request, "grant_id": str(other.id), "installation_key": key, "request_id": str(uuid4()), "node_id": str(uuid4())}
        )


def test_heartbeat_without_verified_package_receipt_cannot_register(environment_request):
    grant, request = environment_request
    EnvironmentInstallService.reserve(**request)
    with pytest.raises(PermissionError, match="receipt"):
        EnvironmentInstallService.validate_registration(
            request["node_id"], {"ip": request["ip"], "tags": [f"zone:{grant.cloud_region_id}", "group:1"]}
        )


def test_installation_key_cannot_call_unlisted_gateway_endpoint(environment_request, settings):
    from django.test import RequestFactory

    from apps.core.openapi.testing import acting_headers, create_system_tenant
    from apps.core.openapi.views import invoke_view

    settings.OPENAPI_INVOKE_TIMEOUT = 0
    _, request = environment_request
    user, key = create_system_tenant(1, username="installer", plaintext_token=request["installation_key"])
    response = invoke_view(RequestFactory().get("/openapi/v1/system-mgmt/groups", **acting_headers(key, user, 1)), "system-mgmt", "groups")
    assert response.status_code == 403
    assert b"SCOPE_DENIED" in response.content


def test_environment_session_cannot_override_signed_architecture(environment_request):
    from apps.core.exceptions.base_app_exception import ValidationAppException
    from apps.node_mgmt.services.installer_session import InstallerSessionService

    grant, request = environment_request
    EnvironmentInstallService.reserve(**request)
    with pytest.raises(ValidationAppException, match="architecture"):
        InstallerSessionService.build_session_config(
            "test-session",
            cpu_architecture="aarch64",
            token_data={
                "node_id": request["node_id"],
                "ip": request["ip"],
                "user": "installer",
                "os": "linux",
                "cpu_architecture": "x86_64",
                "package_id": grant.package_id,
                "cloud_region_id": grant.cloud_region_id,
                "organizations": [1],
                "node_name": "host-b",
                "remaining_usage": 5,
                "environment_grant_id": str(grant.id),
            },
        )


def test_client_failure_report_does_not_forge_registration(environment_request):
    _, request = environment_request
    attempt = EnvironmentInstallService.reserve(**request)
    identity = {k: request[k] for k in ("grant_id", "installation_key", "team", "user_info")}
    result = EnvironmentInstallService.status(**identity, install_id=attempt["install_id"], report={"stage": "install", "error_code": 40})
    assert result["status"] == "pending"
    assert result["failure_stage"] == "install"
    assert result["error_code"] == 40
    result = EnvironmentInstallService.status(**identity, install_id=attempt["install_id"], report={"stage": "complete", "error_code": 0})
    assert result["status"] == "pending"


def test_required_components_cannot_be_replaced_by_registration_success(environment_request):
    from apps.node_mgmt.models import Collector, EnvironmentInstallAttempt, Node, NodeOrganization

    original, request = environment_request
    collector = Collector.objects.create(
        id="environment-telegraf",
        name="Telegraf",
        service_type="exec",
        node_operating_system="linux",
        cpu_architecture="x86_64",
        executable_path="/opt/fusion-collectors/bin/telegraf",
        execute_parameters="--config",
        controller_default_run=True,
        default_config={"nats": "test configuration"},
    )
    grant, key = EnvironmentInstallService.create(
        owner=original.owner,
        domain=original.domain,
        team=original.team,
        cloud_region_id=original.cloud_region_id,
        package_id=original.package_id,
        expires_at=timezone.now() + timedelta(hours=1),
        max_nodes=2,
        required_collectors=[collector.id],
    )
    request.update(grant_id=str(grant.id), installation_key=key)
    result = EnvironmentInstallService.reserve(**request)
    receipt = [f"environment_install:{result['install_id']}", f"environment_package_sha256:{grant.package_sha256}"]
    node = Node.objects.create(
        id=request["node_id"],
        name=request["node_name"],
        ip=request["ip"],
        operating_system="linux",
        cloud_region=grant.cloud_region,
        tags=receipt,
        collector_configuration_directory="/opt/fusion-collectors/generated",
        status={"collectors": [{"collector_id": collector.id, "status": 2}]},
    )
    NodeOrganization.objects.create(node=node, organization=grant.team)
    EnvironmentInstallAttempt.objects.filter(pk=result["install_id"]).update(registered_at=timezone.now(), last_heartbeat_at=timezone.now())
    identity = {k: request[k] for k in ("grant_id", "installation_key", "team", "user_info")}
    failed = EnvironmentInstallService.status(**identity, install_id=result["install_id"])
    assert failed["status"] == "registered"
    assert failed["components_healthy"] is False
    assert failed["components"] == [{"id": collector.id, "name": "Telegraf", "status": "unhealthy"}]
    node.status = {"collectors": [{"collector_id": collector.id, "status": 0}]}
    node.save(update_fields=["status"])
    healthy = EnvironmentInstallService.status(**identity, install_id=result["install_id"])
    assert healthy["components_healthy"] is True
    assert healthy["components"][0]["status"] == "healthy"
    EnvironmentInstallAttempt.objects.filter(pk=result["install_id"]).update(last_heartbeat_at=timezone.now() - timedelta(minutes=5))
    stale = EnvironmentInstallService.status(**identity, install_id=result["install_id"])
    assert stale["status"] == "pending"
    assert stale["components_healthy"] is False


def test_required_component_selection_rejects_unsupported_definition(environment_request):
    from apps.node_mgmt.models import Collector

    grant, _ = environment_request
    collector = Collector.objects.create(
        id="windows-only",
        name="Windows probe",
        service_type="exec",
        node_operating_system="windows",
        cpu_architecture="x86_64",
        executable_path="probe.exe",
        execute_parameters="",
        controller_default_run=True,
        default_config={"nats": "test"},
    )
    with pytest.raises(ValueError, match="unsupported required collector"):
        EnvironmentInstallService.create(
            owner=grant.owner,
            domain=grant.domain,
            team=grant.team,
            cloud_region_id=grant.cloud_region_id,
            package_id=grant.package_id,
            expires_at=timezone.now() + timedelta(hours=1),
            max_nodes=1,
            required_collectors=[collector.id],
        )


def test_environment_registration_assigns_only_selected_components(environment_request):
    from apps.node_mgmt.models import Collector, Node, NodeCollectorConfiguration
    from apps.node_mgmt.services.sidecar import Sidecar

    grant, request = environment_request
    for component_id, name in [("selected-probe", "Selected probe"), ("other-probe", "Other probe")]:
        Collector.objects.create(
            id=component_id,
            name=name,
            service_type="exec",
            node_operating_system="linux",
            cpu_architecture="x86_64",
            executable_path="/opt/fusion-collectors/bin/probe",
            execute_parameters="",
            controller_default_run=True,
            default_config={"nats": "test_configuration = true"},
        )
    grant.required_components = [{"id": "selected-probe", "name": "Selected probe"}]
    grant.save(update_fields=["required_components"])
    EnvironmentInstallService.reserve(**request)
    node = Node.objects.create(
        id=request["node_id"],
        name=request["node_name"],
        ip=request["ip"],
        operating_system="linux",
        cpu_architecture="x86_64",
        cloud_region=grant.cloud_region,
        collector_configuration_directory="/opt/fusion-collectors/generated",
    )
    Sidecar.create_default_config(node, [])
    assigned = list(NodeCollectorConfiguration.objects.filter(node=node).values_list("collector_config__collector_id", flat=True))
    assert assigned == ["selected-probe"]


@pytest.mark.parametrize("rpc_result", [None, {"success": True, "instance_id": "another-node"}, {"success": False}, "no-responder"])
def test_executor_heartbeat_cannot_replace_rpc_readiness(environment_request, monkeypatch, rpc_result):
    from apps.node_mgmt.models import EnvironmentInstallAttempt, Node, NodeOrganization
    from apps.rpc.executor import Executor

    grant, request = environment_request
    grant.required_components = [{"id": "natsexecutor_linux", "name": "NATS-Executor"}]
    grant.save(update_fields=["required_components"])
    attempt = EnvironmentInstallService.reserve(**request)
    node = Node.objects.create(
        id=request["node_id"],
        name=request["node_name"],
        ip=request["ip"],
        operating_system="linux",
        cloud_region=grant.cloud_region,
        collector_configuration_directory="/opt/fusion-collectors/generated",
        tags=[f"environment_install:{attempt['install_id']}", f"environment_package_sha256:{grant.package_sha256}"],
        status={"collectors": [{"collector_id": "natsexecutor_linux", "status": 0}]},
    )
    NodeOrganization.objects.create(node=node, organization=grant.team)
    EnvironmentInstallAttempt.objects.filter(pk=attempt["install_id"]).update(registered_at=timezone.now(), last_heartbeat_at=timezone.now())
    identity = {key: request[key] for key in ("grant_id", "installation_key", "team", "user_info")}

    def probe(self, timeout):
        if rpc_result == "no-responder":
            from nats.errors import NoRespondersError

            raise NoRespondersError
        return rpc_result

    monkeypatch.setattr(Executor, "health_check", probe)
    result = EnvironmentInstallService.status(**identity, install_id=attempt["install_id"])
    assert result["status"] == "registered"
    assert result["components_healthy"] is False
    assert result["executor_rpc_ready"] is False
    monkeypatch.setattr(Executor, "health_check", lambda self, timeout: {"success": True, "instance_id": node.id})
    result = EnvironmentInstallService.status(**identity, install_id=attempt["install_id"])
    assert result["components_healthy"] is True
    assert result["executor_rpc_ready"] is True


def test_result_rows_report_component_health_and_executor_rpc(environment_request, monkeypatch):
    from apps.node_mgmt.models import EnvironmentInstallAttempt, Node
    from apps.rpc.executor import Executor

    grant, request = environment_request
    grant.required_components = [{"id": "natsexecutor_linux", "name": "NATS-Executor"}]
    grant.save(update_fields=["required_components"])
    pending = EnvironmentInstallService.reserve(**request)
    registered_request = {**request, "request_id": str(uuid4()), "node_id": str(uuid4()), "ip": "192.0.2.21", "node_name": "host-c"}
    registered = EnvironmentInstallService.reserve(**registered_request)
    Node.objects.create(
        id=registered_request["node_id"],
        name="host-c",
        ip="192.0.2.21",
        operating_system="linux",
        cloud_region=grant.cloud_region,
        collector_configuration_directory="/opt/fusion-collectors/generated",
        status={"collectors": [{"collector_id": "natsexecutor_linux", "status": 0}]},
    )
    EnvironmentInstallAttempt.objects.filter(pk=registered["install_id"]).update(
        registered_at=timezone.now(),
        last_heartbeat_at=timezone.now(),
    )
    monkeypatch.setattr(Executor, "health_check", lambda self, timeout: {"success": True, "instance_id": self.instance_id})
    row_fields = ("id", "node_id", "node_name", "registered_at", "created_at", "last_heartbeat_at", "failure_stage", "error_code")
    rows = list(grant.attempts.order_by("node_name").values(*row_fields))
    described = {item["node_name"]: item for item in EnvironmentInstallService.describe_attempts(grant, rows)}
    assert described["host-b"]["components_healthy"] is False
    assert described["host-b"]["executor_rpc_ready"] is False
    assert described["host-c"]["components_healthy"] is True
    assert described["host-c"]["executor_rpc_ready"] is True
    EnvironmentInstallAttempt.objects.filter(pk=registered["install_id"]).update(last_heartbeat_at=timezone.now() - timedelta(minutes=5))
    stale_rows = list(grant.attempts.order_by("node_name").values(*row_fields))
    stale = {item["node_name"]: item for item in EnvironmentInstallService.describe_attempts(grant, stale_rows)}
    assert stale["host-c"]["components_healthy"] is False
    assert stale["host-c"]["executor_rpc_ready"] is False
    assert pending["install_id"]
