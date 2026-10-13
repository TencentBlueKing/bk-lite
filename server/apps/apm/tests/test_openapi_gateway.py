"""统一 OpenAPI 网关：APM 只读目录双租户契约。"""

import uuid
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.apm.services.contracts import ServiceRed, SpanDetail, TraceDetail, TracePage, TraceSummary
from apps.apm.models import (
    ApmApplication,
    ApmApplicationOrganization,
    ApmService,
    ApmServiceInstance,
    ApmServiceInstanceOrganization,
    ApmServiceOrganization,
)
from apps.base.models import User, UserAPISecret
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SystemUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

APPLICATIONS_URL = "/openapi/v1/apm/applications"
SERVICES_URL = "/openapi/v1/apm/services"
INSTANCES_URL = "/openapi/v1/apm/instances"
METRICS_URL = "/openapi/v1/apm/services/metrics"
TRACES_URL = "/openapi/v1/apm/traces"
TRACE_DETAIL_URL = "/openapi/v1/apm/traces/detail"


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _grant(system_user):
    names = ["applications-View", "services-View", "integration_instances-View", "traces-View"]
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
