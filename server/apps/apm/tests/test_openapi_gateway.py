"""统一 OpenAPI 网关：APM 只读目录双租户契约。"""

import uuid
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

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


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _grant(system_user):
    names = ["applications-View", "services-View", "integration_instances-View"]
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
