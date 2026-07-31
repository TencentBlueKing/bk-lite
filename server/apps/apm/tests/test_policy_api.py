from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.apm.models import ApmPolicy, ApmService, ApmServiceOrganization


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
        "name": "生产错误率",
        "service_id": str(service.id),
        "environment": "production",
        "metric_type": "error_rate",
        "comparator": "gt",
        "threshold": "0.050000",
        "duration_window": 2,
        "recovery_window": 2,
        "severity": "error",
        "is_enabled": True,
    }


def test_policy_crud_is_scoped_by_service_organization(apm_api_client):
    visible_service = _service(10)
    hidden_service = _service(20, "billing")

    created = apm_api_client.post("/api/v1/apm/policies/", _payload(visible_service), format="json")
    hidden = apm_api_client.post("/api/v1/apm/policies/", _payload(hidden_service), format="json")
    listed = apm_api_client.get("/api/v1/apm/policies/")

    assert created.status_code == 201
    assert created.data["service_name"] == "checkout"
    assert created.data["state"]["status"] == "normal"
    assert hidden.status_code == 404
    assert [item["id"] for item in listed.data] == [created.data["id"]]

    disabled = apm_api_client.post(f"/api/v1/apm/policies/{created.data['id']}/disable/")
    assert disabled.status_code == 200
    assert disabled.data["is_enabled"] is False

    updated = apm_api_client.patch(
        f"/api/v1/apm/policies/{created.data['id']}/",
        {"threshold": "0.100000"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["threshold"] == "0.100000"

    deleted = apm_api_client.delete(f"/api/v1/apm/policies/{created.data['id']}/")
    # 全局 API envelope 将空响应规范化为 200。
    assert deleted.status_code == 200
    assert ApmPolicy.objects.count() == 0


def test_policy_mutation_requires_operate_permission(apm_user):
    apm_user.permission["apm"] = {"policies-View"}
    client = APIClient()
    client.force_authenticate(user=apm_user)
    client.cookies["current_team"] = "10"

    response = client.post("/api/v1/apm/policies/", _payload(_service(10)), format="json")

    assert response.status_code == 403
    assert ApmPolicy.objects.count() == 0


def test_error_rate_threshold_is_bounded(apm_api_client):
    payload = _payload(_service(10))
    payload["threshold"] = "1.100000"

    response = apm_api_client.post("/api/v1/apm/policies/", payload, format="json")

    assert response.status_code == 400
    assert "threshold" in response.data


def test_policy_test_query_uses_controlled_metric_service(apm_api_client, mocker):
    created = apm_api_client.post("/api/v1/apm/policies/", _payload(_service(10)), format="json")
    query_result = SimpleNamespace(
        value=Decimal("0.125"),
        breached=True,
        evaluated_at=timezone.now(),
    )
    service = mocker.Mock()
    service.test_query.return_value = query_result
    mocker.patch("apps.apm.views.control_plane.ApmPolicyViewSet._service", return_value=service)

    response = apm_api_client.post(f"/api/v1/apm/policies/{created.data['id']}/test-query/")

    assert response.status_code == 200
    assert response.data["value"] == "0.125"
    assert response.data["breached"] is True


def test_event_view_uses_current_organization_and_apm_reader(apm_api_client, mocker):
    event = {
        "id": 1,
        "event_id": "EVENT-1",
        "title": "APM 生产错误率触发",
        "severity": "error",
        "action": "created",
    }
    reader = mocker.patch("apps.apm.views.control_plane.ApmEventViewSet.reader")
    reader.list.return_value = [event]

    response = apm_api_client.get("/api/v1/apm/events/?action=created&severity=error&limit=20")

    assert response.status_code == 200
    assert response.data == [event]
    call = reader.list.call_args.kwargs
    assert call["organization_id"] == 10
    assert call["action"] == "created"
    assert call["severity"] == "error"
    assert call["limit"] == 20
