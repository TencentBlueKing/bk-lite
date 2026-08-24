from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.apm.models import ApmDeploymentEvent, ApmService, ApmServiceOrganization


pytestmark = pytest.mark.django_db


def _service(organization=10, name="checkout", *, archived_at=None):
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name=name,
        normalized_name=name,
        first_seen_at=now,
        last_seen_at=now,
        archived_at=archived_at,
        archive_reason="manual" if archived_at else "",
    )
    ApmServiceOrganization.objects.create(service=service, organization=organization)
    return service


def _event(service, *, version, environment="production", status=ApmDeploymentEvent.Status.SUCCESS, deployed_at=None, deployed_by=""):
    return ApmDeploymentEvent.objects.create(
        service=service,
        environment=environment,
        version=version,
        deployed_at=deployed_at or timezone.now(),
        deployed_by=deployed_by,
        status=status,
        source=ApmDeploymentEvent.Source.INFERRED,
    )


def test_deployment_list_is_isolated_by_organization(apm_api_client):
    now = timezone.now()
    visible = _service(10, "checkout")
    other = _service(20, "billing")
    visible_event = _event(visible, version="1.2.0", deployed_at=now - timedelta(hours=1))
    _event(other, version="9.9.9", deployed_at=now - timedelta(minutes=30))

    org_ten = apm_api_client.get("/api/v1/apm/deployments/", {"page_size": 20})
    apm_api_client.cookies["current_team"] = "20"
    org_twenty = apm_api_client.get("/api/v1/apm/deployments/", {"page_size": 20})

    assert org_ten.status_code == org_twenty.status_code == 200
    assert [item["id"] for item in org_ten.data["items"]] == [str(visible_event.id)]
    assert [item["service_name"] for item in org_ten.data["items"]] == ["checkout"]
    assert [item["id"] for item in org_twenty.data["items"]] == [str(ApmDeploymentEvent.objects.get(version="9.9.9").id)]
    assert all(item["service_name"] != "billing" for item in org_ten.data["items"])
    assert all(item["service_name"] != "checkout" for item in org_twenty.data["items"])


def test_deployment_list_requires_services_view_permission(apm_user_without_permissions):
    client = APIClient()
    client.force_authenticate(user=apm_user_without_permissions)
    client.cookies["current_team"] = "10"

    response = client.get("/api/v1/apm/deployments/", {"page_size": 20})

    assert response.status_code == 403


def test_deployment_list_filters_by_service_environment_and_status(apm_api_client):
    now = timezone.now()
    checkout = _service(10, "checkout")
    payment = _service(10, "payment")
    matched = _event(
        checkout,
        version="1.2.0",
        environment="production",
        status=ApmDeploymentEvent.Status.SUCCESS,
        deployed_at=now - timedelta(hours=2),
    )
    _event(
        checkout,
        version="1.3.0-rc",
        environment="staging",
        status=ApmDeploymentEvent.Status.IN_PROGRESS,
        deployed_at=now - timedelta(hours=1),
    )
    _event(
        checkout,
        version="1.1.0",
        environment="production",
        status=ApmDeploymentEvent.Status.ROLLBACK,
        deployed_at=now - timedelta(hours=3),
    )
    _event(
        payment,
        version="2.0.0",
        environment="production",
        status=ApmDeploymentEvent.Status.SUCCESS,
        deployed_at=now - timedelta(minutes=10),
    )

    response = apm_api_client.get(
        "/api/v1/apm/deployments/",
        {
            "page_size": 20,
            "service_id": str(checkout.id),
            "environment": "  production  ",
            "status": "success",
        },
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["items"][0]["id"] == str(matched.id)
    assert response.data["items"][0]["environment"] == "production"
    assert response.data["items"][0]["source"] == "inferred"


def test_deployment_list_defaults_to_seven_days_and_rejects_windows_over_ninety_days(apm_api_client):
    now = timezone.now()
    service = _service(10, "checkout")
    recent = _event(service, version="1.2.0", deployed_at=now - timedelta(days=2))
    _event(service, version="1.0.0", deployed_at=now - timedelta(days=8))

    listed = apm_api_client.get("/api/v1/apm/deployments/", {"page_size": 20})
    too_wide = apm_api_client.get(
        "/api/v1/apm/deployments/",
        {
            "page_size": 20,
            "started_at": (now - timedelta(days=91)).isoformat(),
            "ended_at": now.isoformat(),
        },
    )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.data["items"]] == [str(recent.id)]
    assert too_wide.status_code == 400


def test_deployment_list_caps_page_size_at_one_hundred(apm_api_client):
    now = timezone.now()
    service = _service(10, "checkout")
    for index in range(101):
        _event(service, version=f"1.0.{index}", deployed_at=now - timedelta(minutes=index))

    response = apm_api_client.get("/api/v1/apm/deployments/", {"page_size": 1000})

    assert response.status_code == 200
    assert response.data["count"] == 101
    assert len(response.data["items"]) == 100


def test_deployment_list_paginates_when_page_size_is_omitted(apm_api_client):
    now = timezone.now()
    service = _service(10, "checkout")
    for index in range(21):
        _event(service, version=f"1.0.{index}", deployed_at=now - timedelta(minutes=index))

    response = apm_api_client.get("/api/v1/apm/deployments/")

    assert response.status_code == 200
    assert response.data["count"] == 21
    assert len(response.data["items"]) == 20


def test_deployment_list_excludes_archived_services(apm_api_client):
    now = timezone.now()
    active = _service(10, "checkout")
    archived = _service(10, "legacy", archived_at=now - timedelta(days=1))
    visible = _event(active, version="1.2.0", deployed_at=now - timedelta(hours=1))
    _event(archived, version="0.9.0", deployed_at=now - timedelta(hours=2))

    response = apm_api_client.get("/api/v1/apm/deployments/", {"page_size": 20})

    assert response.status_code == 200
    assert [item["id"] for item in response.data["items"]] == [str(visible.id)]
