import pytest

from apps.apm.models import ApmService, ApmServiceInstance, ApmServiceOrganization
from apps.apm.services.contracts import ServiceRed
from django.utils import timezone


pytestmark = pytest.mark.django_db


def _service(organization=10, name="checkout"):
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name=name,
        normalized_name=name,
        first_seen_at=now,
        last_seen_at=now,
    )
    ApmServiceOrganization.objects.create(service=service, organization=organization)
    ApmServiceInstance.objects.create(
        service=service,
        instance_id=f"{name}-1",
        normalized_instance_id=f"{name}-1",
        environment="production",
        first_seen_at=now,
        last_seen_at=now,
    )
    return service


def test_dashboard_api_returns_empty_payload_without_services(apm_api_client, mocker):
    mocker.patch(
        "apps.apm.views.dashboard.VictoriaTracesTelemetryStore",
        return_value=object(),
    )

    response = apm_api_client.get("/api/v1/apm/dashboard/")

    assert response.status_code == 200
    assert response.data["empty"] is True
    assert response.data["releases"]["status"] == "empty"


def test_dashboard_api_accepts_window_and_scopes_by_organization(apm_api_client, mocker):
    _service(10, "checkout")
    _service(20, "hidden")

    class Store:
        def service_red(self, query):
            return ServiceRed(1.0, 0.0, 100.0, 120.0)

        def slo_measurement(self, query):
            from apps.apm.services.contracts import SloMeasurement

            return SloMeasurement(None, None, None, "no_data")

    mocker.patch("apps.apm.views.dashboard.VictoriaTracesTelemetryStore", return_value=Store())

    response = apm_api_client.get("/api/v1/apm/dashboard/?window=15m")

    assert response.status_code == 200
    assert response.data["empty"] is False
    assert response.data["window"] == "15m"
    assert response.data["kpis"]["data"]["service_count"] == 1
    assert response.data["releases"]["status"] == "empty"


def test_dashboard_api_rejects_invalid_window(apm_api_client):
    response = apm_api_client.get("/api/v1/apm/dashboard/?window=2h")

    assert response.status_code == 400
    assert response.data["code"] == "invalid_query"


def test_dashboard_api_requires_permission(apm_user_without_permissions):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=apm_user_without_permissions)
    client.cookies["current_team"] = "10"

    response = client.get("/api/v1/apm/dashboard/")

    assert response.status_code in {403, 401}
