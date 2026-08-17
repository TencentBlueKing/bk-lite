from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.apm.models import ApmPolicy, ApmService, ApmServiceOrganization

pytestmark = pytest.mark.django_db


def _service(organization=10):
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name=f"checkout-{organization}",
        normalized_name=f"checkout-{organization}",
        first_seen_at=now,
        last_seen_at=now,
    )
    ApmServiceOrganization.objects.create(service=service, organization=organization)
    return service


def _payload(service):
    return {
        "name": "结账错误率",
        "alert_name": "${service} 错误率超过 ${threshold}",
        "service_id": str(service.id),
        "environment": "production",
        "endpoints": ["POST /checkout", "GET /cart"],
        "version_mode": "specific",
        "versions": ["v2"],
        "metric_type": "error_rate",
        "evaluation_interval": 1,
        "metric_window": 5,
        "aggregation": "max",
        "thresholds": [
            {"severity": "critical", "comparator": "gt", "value": "0.20"},
            {"severity": "error", "comparator": "gt", "value": "0.10"},
            {"severity": "warning", "comparator": "gt", "value": "0.05"},
        ],
        "trigger_after": 2,
        "recover_after": 3,
        "no_data_after": 5,
        "no_data_severity": "error",
        "notification_targets": [],
    }


def test_policy_contract_accepts_apm_dimensions_and_never_exposes_arbitrary_query_fields(apm_api_client):
    payload = _payload(_service())
    payload["query"] = "* | stats count()"

    rejected = apm_api_client.post("/api/v1/apm/policies/", payload, format="json")
    payload.pop("query")
    created = apm_api_client.post("/api/v1/apm/policies/", payload, format="json")

    assert rejected.status_code == 400
    assert created.status_code == 201
    assert created.data["endpoints"] == ["POST /checkout", "GET /cart"]
    assert created.data["versions"] == ["v2"]
    assert created.data["thresholds"][0]["severity"] == "critical"
    assert "query" not in created.data
    assert "monitor_object" not in created.data
    assert "log_groups" not in created.data


@pytest.mark.parametrize(
    ("updates", "field"),
    [
        ({"environment": ""}, "environment"),
        ({"version_mode": "specific", "versions": []}, "versions"),
        ({"no_data_after": 5, "no_data_severity": ""}, "no_data_severity"),
        (
            {
                "thresholds": [
                    {"severity": "critical", "comparator": "gt", "value": "0.05"},
                    {"severity": "warning", "comparator": "gt", "value": "0.20"},
                ]
            },
            "thresholds",
        ),
    ],
)
def test_policy_validation_rejects_ambiguous_or_incomplete_semantics(apm_api_client, updates, field):
    payload = _payload(_service())
    payload.update(updates)

    response = apm_api_client.post("/api/v1/apm/policies/", payload, format="json")

    assert response.status_code == 400
    assert field in response.data


def test_policy_preview_queries_real_adapter_without_persisting_a_policy(apm_api_client, mocker):
    service = mocker.Mock()
    service.test_query.return_value = SimpleNamespace(
        value=Decimal("0.12"),
        breached=True,
        evaluated_at=timezone.now(),
        data_state="available",
        threshold={"severity": "error", "comparator": "gt", "value": "0.10"},
        series=(),
    )
    mocker.patch("apps.apm.views.control_plane.ApmPolicyViewSet._service", return_value=service)

    response = apm_api_client.post("/api/v1/apm/policies/preview/", _payload(_service()), format="json")

    assert response.status_code == 200
    assert response.data["value"] == "0.12"
    assert response.data["threshold"]["severity"] == "error"
    assert ApmPolicy.objects.count() == 0
    assert service.test_query.call_args.args[0].environment == "production"
