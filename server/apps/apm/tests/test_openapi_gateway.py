"""统一 OpenAPI 网关：APM 只读目录双租户契约。"""

import uuid
from types import SimpleNamespace

import pytest
from django.utils import timezone
from jsonschema import Draft7Validator
from rest_framework.test import APIClient

from apps.apm.models import (
    ApmApplication,
    ApmApplicationOrganization,
    ApmService,
    ApmServiceInstance,
    ApmServiceInstanceOrganization,
    ApmServiceOrganization,
)
from apps.apm.services.contracts import ServiceRed, SpanDetail, TraceDetail, TracePage, TraceSummary
from apps.base.models import User, UserAPISecret
from apps.core.openapi.testing import acting_headers, create_system_tenant
from apps.system_mgmt.models import Group, Menu, Role, SystemAPIToken
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

APPLICATIONS_URL = "/openapi/v1/apm/applications"
DOCS_URL = "/openapi/v1/_docs"
SERVICES_URL = "/openapi/v1/apm/services"
INSTANCES_URL = "/openapi/v1/apm/instances"
METRICS_URL = "/openapi/v1/apm/services/metrics"
TRACES_URL = "/openapi/v1/apm/traces"
TRACE_DETAIL_URL = "/openapi/v1/apm/traces/detail"
CREATE_APPLICATION_URL = "/openapi/v1/apm/applications"
REGIONS_URL = "/openapi/v1/apm/integration-regions"
CONFIG_URL = "/openapi/v1/apm/integration-configs"


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _application_response_schema(method, auth):
    response = APIClient().get(DOCS_URL, **auth)
    assert response.status_code == 200, response.json()
    apm = next(service for service in response.json()["data"]["services"] if service["name"] == "apm")
    endpoint = next(item for item in apm["endpoints"] if item["path"] == "apm/applications" and item["method"] == method)
    schema = endpoint["response_schema"]
    Draft7Validator.check_schema(schema)
    return schema


def _grant(system_user):
    names = [
        "applications-View",
        "applications-Operate",
        "services-View",
        "integration_instances-View",
        "traces-View",
        "integration_add-View",
    ]
    menu_ids = []
    for name in names:
        menu, _ = Menu.objects.get_or_create(
            name=name,
            app="apm",
            defaults={"display_name": name, "url": "", "menu_type": "button"},
        )
        menu_ids.append(menu.id)
    role, _ = Role.objects.update_or_create(name="openapi-apm-reader", app="apm", defaults={"menu_list": menu_ids})
    system_user.role_list = [role.id]
    system_user.save(update_fields=["role_list"])


def _make_tenant(*, team_name, username, domain):
    team = Group.objects.create(name=f"{team_name}-{uuid.uuid4().hex[:8]}")
    user = User.objects.create(username=f"{username}-{uuid.uuid4().hex[:8]}", domain=domain)
    system_user = SystemUser.objects.create(username=user.username, domain=user.domain, group_list=[team.id])
    _grant(system_user)
    token = UserAPISecret.generate_api_secret()
    UserAPISecret.objects.create(
        username=user.username,
        domain=user.domain,
        api_secret=UserAPISecret.hash_api_secret(token),
        team=team.id,
    )
    return SimpleNamespace(team=team, user=user, token=token)


@pytest.fixture
def tenants():
    return SimpleNamespace(
        a=_make_tenant(team_name="apm-gw-a", username="apm-gw-a", domain="a.test.com"),
        b=_make_tenant(team_name="apm-gw-b", username="apm-gw-b", domain="b.test.com"),
    )


@pytest.fixture
def local_docs_catalog(monkeypatch):
    monkeypatch.setattr("apps.core.openapi.renderer.get_external_catalog", lambda: [])


def _application(*, organization, builtin=False):
    suffix = uuid.uuid4().hex[:6]
    application = ApmApplication.objects.create(
        application_id=f"app-{suffix}",
        name=f"应用-{suffix}",
        is_builtin=builtin,
    )
    if organization is not None:
        ApmApplicationOrganization.objects.create(application=application, organization=organization)
    return application


def _service(application, organization):
    now = timezone.now()
    suffix = uuid.uuid4().hex[:6]
    service = ApmService.objects.create(
        application=application,
        name=f"svc-{suffix}",
        normalized_name=f"svc-{suffix}",
        first_seen_at=now,
        last_seen_at=now,
    )
    ApmServiceOrganization.objects.create(service=service, organization=organization)
    return service


def _instance(service, organization):
    now = timezone.now()
    suffix = uuid.uuid4().hex[:6]
    instance = ApmServiceInstance.objects.create(
        service=service,
        instance_id=f"pod-{suffix}",
        normalized_instance_id=f"pod-{suffix}",
        first_seen_at=now,
        last_seen_at=now,
    )
    ApmServiceInstanceOrganization.objects.create(instance=instance, organization=organization)
    return instance


def test_api_tenant_can_list_own_applications(tenants):
    own = _application(organization=tenants.a.team.id)
    other = _application(organization=tenants.b.team.id)
    builtin = _application(organization=tenants.a.team.id, builtin=True)
    unassigned = _application(organization=None)

    response = APIClient().get(APPLICATIONS_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    ids = {item["application_id"] for item in response.json()["data"]["items"]}
    assert own.application_id in ids
    assert other.application_id not in ids
    assert builtin.application_id not in ids
    assert unassigned.application_id not in ids


def test_application_create_and_list_responses_match_published_contract(tenants, local_docs_catalog):
    application_id = f"contract-{uuid.uuid4().hex[:6]}"
    payload = {
        "application_id": application_id,
        "name": "契约应用",
        "description": "由 OpenAPI 创建后查回",
    }

    created = APIClient().post(
        APPLICATIONS_URL,
        payload,
        format="json",
        **_auth(tenants.a.token),
    )
    assert created.status_code == 200, created.json()
    Draft7Validator(_application_response_schema("POST", _auth(tenants.a.token))).validate(created.json())

    listed = APIClient().get(
        APPLICATIONS_URL,
        {"keyword": application_id},
        **_auth(tenants.a.token),
    )
    assert listed.status_code == 200, listed.json()
    Draft7Validator(_application_response_schema("GET", _auth(tenants.a.token))).validate(listed.json())
    assert listed.json()["data"] == {
        "count": 1,
        "page": 1,
        "page_size": 20,
        "items": [{"id": created.json()["data"]["id"], **payload}],
    }


def test_empty_application_list_matches_published_contract(tenants, local_docs_catalog):
    response = APIClient().get(APPLICATIONS_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    Draft7Validator(_application_response_schema("GET", _auth(tenants.a.token))).validate(response.json())
    assert response.json()["data"] == {
        "count": 0,
        "page": 1,
        "page_size": 20,
        "items": [],
    }


def test_system_token_application_scope_allows_get_and_rejects_post(local_docs_catalog):
    team = Group.objects.create(name=f"apm-system-{uuid.uuid4().hex[:8]}")
    user, token = create_system_tenant(
        team.id,
        username=f"apm-system-{uuid.uuid4().hex[:8]}",
        system_id="itsm",
        scope={"mode": "allowlist", "endpoints": ["GET apm/applications"]},
    )
    _grant(SystemUser.objects.get(username=user.username, domain=user.domain))
    own = _application(organization=team.id)
    auth = acting_headers(token, user, team.id)

    listed = APIClient().get(APPLICATIONS_URL, **auth)

    assert listed.status_code == 200, listed.json()
    Draft7Validator(_application_response_schema("GET", auth)).validate(listed.json())
    assert [item["application_id"] for item in listed.json()["data"]["items"]] == [own.application_id]

    denied = APIClient().post(
        APPLICATIONS_URL,
        {"application_id": f"denied-{uuid.uuid4().hex[:6]}", "name": "无 Scope"},
        format="json",
        **auth,
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "SCOPE_DENIED"


def test_itsm_system_token_creates_and_reads_application_in_fixed_acting_org(tenants, local_docs_catalog):
    token = SystemAPIToken.generate_secret()
    SystemAPIToken.objects.create(
        system_id="itsm",
        name="ITSM APM 联调",
        secret_hash=SystemAPIToken.hash_secret(token),
        scope={
            "mode": "allowlist",
            "endpoints": ["GET apm/applications", "POST apm/applications"],
        },
        enabled=True,
        created_by="admin",
        created_by_domain="domain.com",
    )
    acting_a = acting_headers(token, tenants.a.user, tenants.a.team.id)
    acting_b = acting_headers(token, tenants.b.user, tenants.b.team.id)
    application_id = f"itsm-{uuid.uuid4().hex[:6]}"
    payload = {
        "application_id": application_id,
        "name": "ITSM 固定身份应用",
        "description": "系统 Token 联调",
    }

    created = APIClient().post(APPLICATIONS_URL, payload, format="json", **acting_a)

    assert created.status_code == 200, created.json()
    Draft7Validator(_application_response_schema("POST", acting_a)).validate(created.json())

    visible = APIClient().get(APPLICATIONS_URL, {"keyword": application_id}, **acting_a)
    assert visible.status_code == 200, visible.json()
    Draft7Validator(_application_response_schema("GET", acting_a)).validate(visible.json())
    assert visible.json()["data"]["items"] == [{"id": created.json()["data"]["id"], **payload}]

    hidden = APIClient().get(APPLICATIONS_URL, {"keyword": application_id}, **acting_b)
    assert hidden.status_code == 200, hidden.json()
    Draft7Validator(_application_response_schema("GET", acting_b)).validate(hidden.json())
    assert hidden.json()["data"]["count"] == 0
    assert hidden.json()["data"]["items"] == []


def test_api_tenant_cannot_list_other_org_applications(tenants):
    other = _application(organization=tenants.a.team.id)

    response = APIClient().get(APPLICATIONS_URL, **_auth(tenants.b.token))

    assert response.status_code == 200, response.json()
    ids = {item["application_id"] for item in response.json()["data"]["items"]}
    assert other.application_id not in ids


def test_applications_forged_team_is_rejected(tenants):
    response = APIClient().get(APPLICATIONS_URL, {"team": str(tenants.b.team.id)}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_list_own_services(tenants):
    application = _application(organization=tenants.a.team.id)
    own = _service(application, tenants.a.team.id)
    other_app = _application(organization=tenants.b.team.id)
    other = _service(other_app, tenants.b.team.id)

    response = APIClient().get(SERVICES_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert str(own.id) in ids
    assert str(other.id) not in ids


def test_api_tenant_cannot_list_other_org_services(tenants):
    application = _application(organization=tenants.a.team.id)
    other = _service(application, tenants.a.team.id)

    response = APIClient().get(SERVICES_URL, **_auth(tenants.b.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert str(other.id) not in ids


def test_services_forged_team_is_rejected(tenants):
    response = APIClient().get(SERVICES_URL, {"team": str(tenants.b.team.id)}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_list_own_instances(tenants):
    application = _application(organization=tenants.a.team.id)
    service = _service(application, tenants.a.team.id)
    own = _instance(service, tenants.a.team.id)
    other_app = _application(organization=tenants.b.team.id)
    other_service = _service(other_app, tenants.b.team.id)
    other = _instance(other_service, tenants.b.team.id)

    response = APIClient().get(INSTANCES_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert str(own.id) in ids
    assert str(other.id) not in ids


def test_api_tenant_cannot_list_other_org_instances(tenants):
    application = _application(organization=tenants.a.team.id)
    service = _service(application, tenants.a.team.id)
    other = _instance(service, tenants.a.team.id)

    response = APIClient().get(INSTANCES_URL, **_auth(tenants.b.token))

    assert response.status_code == 200, response.json()
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert str(other.id) not in ids


def test_instances_forged_team_is_rejected(tenants):
    response = APIClient().get(INSTANCES_URL, {"team": str(tenants.b.team.id)}, **_auth(tenants.a.token))

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


class _Telemetry:
    def __init__(self, *, red=None, page=None, detail=None):
        self.red = red
        self.page = page or TracePage(items=(), next_cursor=None)
        self.detail = detail

    def service_red(self, query):
        return self.red

    def search_traces(self, query):
        return self.page

    def get_trace(self, trace_id):
        return self.detail


def test_api_tenant_can_query_own_service_metrics(tenants, monkeypatch):
    application = _application(organization=tenants.a.team.id)
    service = _service(application, tenants.a.team.id)
    monkeypatch.setattr(
        "apps.apm.openapi_service._telemetry",
        lambda: _Telemetry(red=ServiceRed(request_rate=1.5, error_rate=0.0, p95_ms=12.0, p99_ms=20.0, request_count=10, error_count=0)),
    )

    response = APIClient().get(
        METRICS_URL,
        {"service_id": str(service.id), "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["request_rate"] == 1.5
    assert response.json()["data"]["service_id"] == str(service.id)


def test_api_tenant_cannot_query_other_org_service_metrics(tenants, monkeypatch):
    application = _application(organization=tenants.a.team.id)
    service = _service(application, tenants.a.team.id)
    monkeypatch.setattr(
        "apps.apm.openapi_service._telemetry",
        lambda: (_ for _ in ()).throw(AssertionError("queried")),
    )

    response = APIClient().get(
        METRICS_URL,
        {"service_id": str(service.id), "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        **_auth(tenants.b.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "服务不存在"


def test_service_metrics_reject_window_over_seven_days(tenants):
    response = APIClient().get(
        METRICS_URL,
        {"service_id": str(uuid.uuid4()), "start": "2026-01-01T00:00:00Z", "end": "2026-01-09T00:00:00Z"},
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "查询时间范围不能超过 7 天"


def test_api_tenant_can_list_own_traces(tenants, monkeypatch):
    application = _application(organization=tenants.a.team.id)
    service = _service(application, tenants.a.team.id)
    now = timezone.now()
    own = TraceSummary(
        trace_id="a" * 32,
        started_at=now,
        duration_ms=10,
        service_namespace="",
        service_name=service.normalized_name,
        environment="",
        instance_id=None,
        status="error",
        root_span_name="GET /pay",
        span_count=2,
    )
    other = TraceSummary(
        trace_id="b" * 32,
        started_at=now,
        duration_ms=8,
        service_namespace="",
        service_name="foreign-service",
        environment="",
        instance_id=None,
        status="ok",
        root_span_name="GET /other",
        span_count=1,
    )
    monkeypatch.setattr("apps.apm.openapi_service._telemetry", lambda: _Telemetry(page=TracePage(items=(own, other), next_cursor=None)))

    response = APIClient().get(
        TRACES_URL,
        {"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:30:00Z", "service_id": str(service.id)},
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    ids = [item["trace_id"] for item in response.json()["data"]["items"]]
    assert ids == ["a" * 32]


def test_traces_reject_window_over_one_hour(tenants, monkeypatch):
    monkeypatch.setattr(
        "apps.apm.openapi_service._telemetry",
        lambda: (_ for _ in ()).throw(AssertionError("queried")),
    )

    response = APIClient().get(
        TRACES_URL,
        {"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T02:00:00Z"},
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "查询时间范围不能超过 1 小时"


def test_api_tenant_cannot_read_other_org_trace(tenants, monkeypatch):
    application = _application(organization=tenants.a.team.id)
    service = _service(application, tenants.a.team.id)
    now = timezone.now()
    detail = TraceDetail(
        trace_id="c" * 32,
        spans=(
            SpanDetail(
                span_id="1" * 16,
                parent_span_id=None,
                name="GET /pay",
                started_at=now,
                duration_ms=4,
                status="ok",
                service_namespace="",
                service_name=service.normalized_name,
            ),
        ),
        service_namespace="",
        service_name=service.normalized_name,
        environment="",
        instance_id=None,
    )
    monkeypatch.setattr("apps.apm.openapi_service._telemetry", lambda: _Telemetry(detail=detail))

    own = APIClient().get(TRACE_DETAIL_URL, {"trace_id": "c" * 32}, **_auth(tenants.a.token))
    other = APIClient().get(TRACE_DETAIL_URL, {"trace_id": "c" * 32}, **_auth(tenants.b.token))

    assert own.status_code == 200, own.json()
    assert own.json()["data"]["spans"][0]["name"] == "GET /pay"
    assert other.status_code == 400
    assert other.json()["message"] == "调用不存在"


def test_api_tenant_creates_application_in_own_org(tenants):
    application_id = f"pay-{uuid.uuid4().hex[:6]}"

    response = APIClient().post(
        CREATE_APPLICATION_URL,
        {"application_id": application_id, "name": "支付"},
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 200, response.json()
    created = ApmApplication.objects.get(application_id=application_id)
    assert list(created.organization_links.values_list("organization", flat=True)) == [tenants.a.team.id]


def test_application_create_forged_team_is_rejected(tenants):
    response = APIClient().post(
        CREATE_APPLICATION_URL,
        {"application_id": "pay", "name": "支付", "organization_ids": [tenants.b.team.id]},
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "SCHEMA_INVALID"


def test_api_tenant_can_list_integration_regions(tenants, monkeypatch):
    monkeypatch.setattr(
        "apps.apm.services.integration_configuration.DjangoIntegrationConfigurationService.list_regions",
        staticmethod(lambda node_mgmt: [{"id": 1, "name": "default"}]),
    )

    response = APIClient().get(REGIONS_URL, **_auth(tenants.a.token))

    assert response.status_code == 200, response.json()
    assert response.json()["data"]["items"] == [{"id": 1, "name": "default"}]


def test_api_tenant_cannot_render_other_org_integration_config(tenants, monkeypatch):
    application = _application(organization=tenants.b.team.id)
    called = {"value": False}

    def _resolve(*args, **kwargs):
        called["value"] = True
        raise AssertionError("should not resolve")

    monkeypatch.setattr(
        "apps.apm.services.integration_configuration.DjangoIntegrationConfigurationService.resolve_region",
        _resolve,
    )
    response = APIClient().post(
        CONFIG_URL,
        {
            "application_id": application.application_id,
            "cloud_region_id": 1,
            "language": "python",
            "runtime": "host",
            "service_name": "pay",
            "environment": "prod",
        },
        format="json",
        **_auth(tenants.a.token),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "应用不存在"
    assert called["value"] is False
