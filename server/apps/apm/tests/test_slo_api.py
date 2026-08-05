from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import TelemetryStoreUnavailable
from apps.apm.models import ApmService, ApmServiceOrganization, ApmSlo
from apps.apm.services.contracts import SloEvaluation


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
    return service


def _payload(service):
    return {
        "name": "结算可用性",
        "service_id": str(service.id),
        "environment": "production",
        "endpoint": "",
        "sli_type": "availability",
        "objective": "99.900",
        "evaluation_window": "rolling30d",
        "is_enabled": True,
    }


def test_slo_crud_is_scoped_and_returns_real_evaluation(apm_api_client, mocker):
    visible = _service(10)
    hidden = _service(20, "billing")
    now = timezone.now()
    evaluate = mocker.patch(
        "apps.apm.views.control_plane.DjangoApmReliabilityService.evaluate",
        return_value=SloEvaluation(
            current_rate=99.95,
            budget_remaining=50,
            data_state="available",
            started_at=now - timedelta(days=30),
            ended_at=now,
        ),
    )

    created = apm_api_client.post("/api/v1/apm/slos/", _payload(visible), format="json")
    denied = apm_api_client.post("/api/v1/apm/slos/", _payload(hidden), format="json")
    listed = apm_api_client.get("/api/v1/apm/slos/")

    assert created.status_code == 201
    assert created.data["service_name"] == "checkout"
    assert created.data["current_rate"] == 99.95
    assert created.data["budget_remaining"] == 50
    assert denied.status_code == 404
    assert [item["id"] for item in listed.data] == [created.data["id"]]
    assert evaluate.call_count >= 2

    disabled = apm_api_client.post(f"/api/v1/apm/slos/{created.data['id']}/disable/")
    assert disabled.status_code == 200
    assert disabled.data["is_enabled"] is False

    updated = apm_api_client.patch(
        f"/api/v1/apm/slos/{created.data['id']}/",
        {"objective": "99.500"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["objective"] == "99.500"

    deleted = apm_api_client.delete(f"/api/v1/apm/slos/{created.data['id']}/")
    assert deleted.status_code == 200
    assert ApmSlo.objects.count() == 0


def test_latency_slo_requires_threshold(apm_api_client):
    payload = _payload(_service())
    payload["sli_type"] = "latency_p95"

    response = apm_api_client.post("/api/v1/apm/slos/", payload, format="json")

    assert response.status_code == 400
    assert "latency_threshold_ms" in response.data


def test_slo_list_degrades_each_evaluation_without_hiding_metadata(apm_api_client, mocker):
    payload = _payload(_service())
    slo = ApmSlo.objects.create(
        name=payload["name"],
        service_id=payload["service_id"],
        environment=payload["environment"],
        sli_type=payload["sli_type"],
        objective=payload["objective"],
        evaluation_window=payload["evaluation_window"],
    )
    mocker.patch(
        "apps.apm.views.control_plane.DjangoApmReliabilityService.evaluate",
        side_effect=TelemetryStoreUnavailable("VictoriaMetrics 查询不可用"),
    )

    response = apm_api_client.get("/api/v1/apm/slos/")

    assert response.status_code == 200
    assert response.data[0]["id"] == str(slo.id)
    assert response.data[0]["data_state"] == "unavailable"
    assert response.data[0]["current_rate"] is None
