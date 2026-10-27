import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher, TelemetryStoreUnavailable
from apps.apm.models import (
    ApmAlert,
    ApmAlertMetricSnapshot,
    ApmAlertOutbox,
    ApmEvent,
    ApmEventSnapshot,
    ApmPolicy,
    ApmPolicyTargetState,
    ApmService,
    ApmServiceOrganization,
)
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import ServiceRed

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
        "organizations": [10],
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


def test_policy_contract_accepts_legal_target_combinations_and_rejects_oversized_specific(apm_api_client):
    service = _service()
    payload = _payload(service)
    payload["endpoints"] = [f"GET /e{i}" for i in range(10)]
    payload["versions"] = [f"v{i}" for i in range(10)]

    created = apm_api_client.post("/api/v1/apm/policies/", payload, format="json")
    assert created.status_code == 201
    assert len(created.data["endpoints"]) == 10
    assert len(created.data["versions"]) == 10

    patched = apm_api_client.patch(
        f"/api/v1/apm/policies/{created.data['id']}/",
        {"endpoints": payload["endpoints"], "versions": payload["versions"]},
        format="json",
    )
    assert patched.status_code == 200

    oversized = {
        **payload,
        "endpoints": ["GET /a", "GET /b"],
        "versions": [f"v{i}" for i in range(100)],
    }
    rejected_create = apm_api_client.post("/api/v1/apm/policies/", oversized, format="json")
    assert rejected_create.status_code == 400

    rejected_patch = apm_api_client.patch(
        f"/api/v1/apm/policies/{created.data['id']}/",
        {"endpoints": oversized["endpoints"], "versions": oversized["versions"]},
        format="json",
    )
    assert rejected_patch.status_code == 400


def _compare_payload(service, **updates):
    payload = _payload(service)
    payload.update(updates)
    return payload


@pytest.mark.parametrize(
    ("updates", "field"),
    [
        ({"compare_mode": "absolute", "compare_value_kind": "percent"}, "compare_value_kind"),
        (
            {"compare_mode": "offset_1h", "compare_value_kind": "delta", "thresholds": [{"severity": "error", "comparator": "gt", "value": "10"}]},
            "compare_value_kind",
        ),
        (
            {"compare_mode": "offset_24h", "compare_value_kind": "delta", "thresholds": [{"severity": "error", "comparator": "gt", "value": "10"}]},
            "compare_value_kind",
        ),
        ({"compare_mode": "previous_window", "compare_value_kind": ""}, "compare_value_kind"),
        (
            {
                "metric_type": "no_traffic",
                "compare_mode": "previous_window",
                "compare_value_kind": "delta",
                "thresholds": [{"severity": "error", "comparator": "lte", "value": "0"}],
            },
            "compare_mode",
        ),
        (
            {"metric_type": "no_traffic", "min_request_count": 20, "thresholds": [{"severity": "error", "comparator": "lte", "value": "0"}]},
            "min_request_count",
        ),
        (
            {"metric_type": "throughput", "min_request_count": 20, "thresholds": [{"severity": "error", "comparator": "gt", "value": "10"}]},
            "min_request_count",
        ),
        (
            {
                "compare_mode": "previous_window",
                "compare_value_kind": "delta",
                "thresholds": [{"severity": "error", "comparator": "gt", "value": "2"}],
            },
            "thresholds",
        ),
    ],
)
def test_policy_compare_rules_reject_illegal_combinations(apm_api_client, updates, field):
    response = apm_api_client.post("/api/v1/apm/policies/", _compare_payload(_service(), **updates), format="json")

    assert response.status_code == 400
    assert field in response.data


@pytest.mark.parametrize(
    "updates",
    [
        {},
        {"compare_mode": "absolute", "compare_value_kind": ""},
        {
            "compare_mode": "previous_window",
            "compare_value_kind": "delta",
            "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.02"}],
        },
        {
            "compare_mode": "previous_window",
            "compare_value_kind": "percent",
            "thresholds": [{"severity": "error", "comparator": "gt", "value": "50"}],
        },
        {"compare_mode": "offset_1h", "compare_value_kind": "percent", "thresholds": [{"severity": "error", "comparator": "gt", "value": "50"}]},
        {"compare_mode": "offset_24h", "compare_value_kind": "percent", "thresholds": [{"severity": "error", "comparator": "gt", "value": "50"}]},
        {
            "metric_type": "no_traffic",
            "compare_mode": "absolute",
            "compare_value_kind": "",
            "thresholds": [{"severity": "error", "comparator": "lte", "value": "0"}],
        },
        {"metric_type": "throughput", "thresholds": [{"severity": "error", "comparator": "gt", "value": "10"}]},
        {"min_request_count": 20},
        {"metric_type": "p95", "min_request_count": 20, "thresholds": [{"severity": "error", "comparator": "gt", "value": "200"}]},
        {"metric_type": "p99", "min_request_count": None, "thresholds": [{"severity": "error", "comparator": "gt", "value": "200"}]},
    ],
)
def test_policy_compare_rules_accept_legal_combinations(apm_api_client, updates):
    response = apm_api_client.post("/api/v1/apm/policies/", _compare_payload(_service(), **updates), format="json")

    assert response.status_code == 201
    assert response.data["compare_mode"] == updates.get("compare_mode", "absolute")
    assert response.data["compare_value_kind"] == updates.get("compare_value_kind", "")
    assert response.data["min_request_count"] == updates.get("min_request_count")


def test_legacy_policy_payload_defaults_compare_fields(apm_api_client):
    created = apm_api_client.post("/api/v1/apm/policies/", _payload(_service()), format="json")

    assert created.status_code == 201
    assert created.data["compare_mode"] == "absolute"
    assert created.data["compare_value_kind"] == ""
    assert created.data["min_request_count"] is None


class ScriptedMetricStore:
    def __init__(self, reds):
        self.reds = list(reds)
        self.queries = []

    def service_red(self, query):
        self.queries.append(query)
        if not self.reds:
            raise RuntimeError("query QUERY_SENTINEL body RESPONSE_SENTINEL")
        if len(self.reds) == 1:
            return self.reds[0]
        return self.reds.pop(0)


class CountingDispatcher:
    def __init__(self):
        self.calls = 0

    def dispatch(self, delivery):
        self.calls += 1
        return None


def _bind_dry_run(mocker, reds):
    store = ScriptedMetricStore(reds)
    dispatcher = CountingDispatcher()
    mocker.patch(
        "apps.apm.views.control_plane.ApmPolicyViewSet._service",
        return_value=DjangoApmPolicyService(store, dispatcher),
    )
    return store, dispatcher


def _side_effect_counts():
    return (
        ApmAlert.objects.count(),
        ApmEvent.objects.count(),
        ApmAlertMetricSnapshot.objects.count(),
        ApmEventSnapshot.objects.count(),
        ApmAlertOutbox.objects.count(),
        ApmPolicyTargetState.objects.count(),
    )


def test_dry_run_reports_each_verdict_without_side_effects(apm_api_client, mocker):
    service = _service()
    before = _side_effect_counts()
    _bind_dry_run(mocker, [ServiceRed(20, 0.12, 100, 150, request_count=80)])
    trigger = apm_api_client.post(
        "/api/v1/apm/policies/dry-run/",
        _compare_payload(service, trigger_after=1),
        format="json",
    )
    assert trigger.status_code == 200
    assert trigger.data["items"][0]["verdict"] == "would_trigger"
    assert trigger.data["items"][0]["matched_threshold"]["severity"] == "error"

    _bind_dry_run(mocker, [ServiceRed(20, 0.01, 100, 150, request_count=80)])
    ok = apm_api_client.post("/api/v1/apm/policies/dry-run/", _compare_payload(service, trigger_after=1), format="json")
    assert ok.data["items"][0]["verdict"] == "ok"

    _bind_dry_run(mocker, [ServiceRed(None, None, None, None)])
    no_data = apm_api_client.post("/api/v1/apm/policies/dry-run/", _compare_payload(service), format="json")
    assert no_data.data["items"][0]["verdict"] == "no_data"

    _bind_dry_run(
        mocker,
        [
            ServiceRed(20, 0.06, 100, 150, request_count=80),
            ServiceRed(None, None, None, None),
        ],
    )
    missing = apm_api_client.post(
        "/api/v1/apm/policies/dry-run/",
        _compare_payload(
            service,
            compare_mode="previous_window",
            compare_value_kind="percent",
            endpoints=["POST /checkout"],
            thresholds=[{"severity": "error", "comparator": "gt", "value": "10"}],
        ),
        format="json",
    )
    assert missing.data["items"][0]["verdict"] == "missing_baseline"
    assert missing.data["items"][0]["reason"] == "对照缺失"

    _bind_dry_run(mocker, [ServiceRed(20, 0.5, 100, 150, request_count=12)])
    short = apm_api_client.post(
        "/api/v1/apm/policies/dry-run/",
        _compare_payload(
            service,
            compare_mode="previous_window",
            compare_value_kind="percent",
            min_request_count=20,
            thresholds=[{"severity": "error", "comparator": "gt", "value": "10"}],
        ),
        format="json",
    )
    assert short.data["items"][0]["verdict"] == "insufficient_samples"
    assert short.data["items"][0]["reason"] == "样本不足"
    assert _side_effect_counts() == before

    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        _compare_payload(service, trigger_after=1, recover_after=3),
        format="json",
    )
    policy = ApmPolicy.objects.get(id=created.data["id"])
    ApmPolicyTargetState.objects.create(
        policy=policy,
        target_key="kept",
        endpoint="POST /checkout",
        version="v2",
        status=ApmPolicyTargetState.Status.ACTIVE,
        current_severity="warning",
        consecutive_hits=4,
        consecutive_recoveries=2,
        consecutive_no_data=1,
        evaluation_cursor="frozen",
        active_alert_id="apm-existing",
    )
    saved_before = _side_effect_counts()
    state_before = list(
        ApmPolicyTargetState.objects.values(
            "consecutive_hits",
            "consecutive_recoveries",
            "consecutive_no_data",
            "status",
            "current_severity",
            "evaluation_cursor",
            "active_alert_id",
        )
    )
    _bind_dry_run(mocker, [ServiceRed(20, 0.01, 100, 150, request_count=80)])
    recover = apm_api_client.post(
        "/api/v1/apm/policies/dry-run/",
        _compare_payload(service, policy_id=created.data["id"], trigger_after=1, recover_after=3),
        format="json",
    )
    assert recover.status_code == 200
    checkout = next(item for item in recover.data["items"] if item["endpoint"] == "POST /checkout")
    assert checkout["verdict"] == "would_recover"
    assert checkout["reason"] == "需连续 3 次"

    _bind_dry_run(mocker, [ServiceRed(20, 0.25, 100, 150, request_count=80)])
    escalate = apm_api_client.post(
        "/api/v1/apm/policies/dry-run/",
        _compare_payload(service, policy_id=created.data["id"], trigger_after=1),
        format="json",
    )
    checkout = next(item for item in escalate.data["items"] if item["endpoint"] == "POST /checkout")
    assert checkout["verdict"] == "would_escalate"
    assert _side_effect_counts() == saved_before
    assert (
        list(
            ApmPolicyTargetState.objects.values(
                "consecutive_hits",
                "consecutive_recoveries",
                "consecutive_no_data",
                "status",
                "current_severity",
                "evaluation_cursor",
                "active_alert_id",
            )
        )
        == state_before
    )


def test_dry_run_truncates_after_twenty_targets_and_explains_consecutive_hits(apm_api_client, mocker):
    service = _service()
    _bind_dry_run(mocker, [ServiceRed(20, 0.12, 100, 150, request_count=80)])
    endpoints = [f"GET /e{i}" for i in range(21)]
    truncated = apm_api_client.post(
        "/api/v1/apm/policies/dry-run/",
        _compare_payload(service, endpoints=endpoints, version_mode="all", versions=[], trigger_after=3),
        format="json",
    )

    assert truncated.status_code == 200
    assert truncated.data["truncated"] is True
    assert truncated.data["total_targets"] == 21
    assert len(truncated.data["items"]) == 20
    assert truncated.data["items"][0]["endpoint"] == "GET /e0"
    assert truncated.data["items"][0]["reason"] == "本轮命中 1/3，现网不会建告警"
    assert "GET /e20" not in {item["endpoint"] for item in truncated.data["items"]}

    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        _compare_payload(service, endpoints=["GET /orders"], version_mode="all", versions=[], trigger_after=3),
        format="json",
    )
    ApmPolicyTargetState.objects.create(
        policy_id=created.data["id"],
        target_key="orders",
        endpoint="GET /orders",
        version="",
        consecutive_hits=1,
    )
    _bind_dry_run(mocker, [ServiceRed(20, 0.12, 100, 150, request_count=80)])
    saved = apm_api_client.post(
        "/api/v1/apm/policies/dry-run/",
        _compare_payload(
            service,
            policy_id=created.data["id"],
            endpoints=["GET /orders"],
            version_mode="all",
            versions=[],
            trigger_after=3,
        ),
        format="json",
    )
    assert saved.data["items"][0]["reason"] == "本轮命中 2/3，现网不会建告警"


def test_dry_run_hides_unauthorized_service_and_policy(apm_api_client, mocker):
    hidden_service = _service(organization=20)
    _bind_dry_run(mocker, [ServiceRed(20, 0.12, 100, 150, request_count=80)])
    hidden = apm_api_client.post(
        "/api/v1/apm/policies/dry-run/",
        _compare_payload(hidden_service),
        format="json",
    )
    assert hidden.status_code == 404

    visible = _service()
    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        {**_payload(visible), "organizations": [20]},
        format="json",
    )
    assert created.status_code == 201
    denied = apm_api_client.post(
        "/api/v1/apm/policies/dry-run/",
        {**_payload(visible), "policy_id": created.data["id"]},
        format="json",
    )
    assert denied.status_code == 404


def test_dry_run_returns_telemetry_unavailable_without_the_failure_warning(apm_api_client, mocker, caplog):
    class UnavailableStore:
        def service_red(self, query):
            raise TelemetryStoreUnavailable("victoriatraces unavailable")

    mocker.patch(
        "apps.apm.views.control_plane.ApmPolicyViewSet._service",
        return_value=DjangoApmPolicyService(UnavailableStore(), InMemoryNotificationDispatcher()),
    )
    caplog.set_level(logging.DEBUG)
    response = apm_api_client.post("/api/v1/apm/policies/dry-run/", _payload(_service()), format="json")

    assert response.status_code == 503
    assert response.data["code"] == "telemetry_unavailable"
    assert not any(record.msg == "event=apm_policy_dry_run_failed policy_id=%s failed_stage=%s error_type=%s" for record in caplog.records)


def test_dry_run_failure_logs_one_warning_without_query_or_response_text(apm_api_client, mocker, caplog):
    class FailingStore:
        def service_red(self, query):
            query_text = "QUERY_" + "SENTINEL"
            response_text = "RESPONSE_" + "SENTINEL"
            raise RuntimeError(f"query {query_text} body {response_text}")

    mocker.patch(
        "apps.apm.views.control_plane.ApmPolicyViewSet._service",
        return_value=DjangoApmPolicyService(FailingStore(), InMemoryNotificationDispatcher()),
    )
    caplog.set_level(logging.DEBUG, logger="apm")
    response = apm_api_client.post("/api/v1/apm/policies/dry-run/", _payload(_service()), format="json")

    warnings = [record for record in caplog.records if record.name == "apm" and record.levelno == logging.WARNING]
    assert response.status_code == 500
    assert response.data["message"] == "试算失败"
    assert response.data["result"] is False
    assert len(warnings) == 1
    record = warnings[0]
    assert record.msg == "event=apm_policy_dry_run_failed policy_id=%s failed_stage=%s error_type=%s"
    assert record.args == ("", "dry_run", "RuntimeError")
    assert record.exc_info is not None
    rendered = logging.Formatter().format(record)
    assert record.getMessage() == "event=apm_policy_dry_run_failed policy_id= failed_stage=dry_run error_type=RuntimeError"
    assert "QUERY_SENTINEL" not in rendered
    assert "RESPONSE_SENTINEL" not in rendered
    for item in caplog.records:
        formatted = logging.Formatter().format(item)
        assert "QUERY_SENTINEL" not in formatted
        assert "RESPONSE_SENTINEL" not in formatted
        assert "QUERY_SENTINEL" not in item.getMessage()
    assert "QUERY_SENTINEL" not in str(response.data)
    assert "Traceback" not in str(response.data)
