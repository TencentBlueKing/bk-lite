import logging
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.adapters.errors import TelemetryStoreUnavailable
from apps.apm.models import ApmPolicy, ApmPolicyNotificationTarget, ApmPolicyTargetState, ApmService, ApmServiceOrganization
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import MetricDataState, ServiceRed
from apps.apm.tests.helpers import bind_policy_organizations

pytestmark = pytest.mark.django_db


def _service(name):
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name=name,
        normalized_name=name,
        first_seen_at=now,
        last_seen_at=now,
    )
    ApmServiceOrganization.objects.create(service=service, organization=10)
    return service


def _payload(service, **updates):
    payload = {
        "name": "近 N 天同窗",
        "service_id": str(service.id),
        "organizations": [10],
        "environment": "production",
        "endpoints": [],
        "version_mode": "all",
        "versions": [],
        "metric_type": "p95",
        "evaluation_interval": 1,
        "metric_window": 5,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "100"}],
        "trigger_after": 1,
        "recover_after": 2,
        "notification_targets": [],
    }
    payload.update(updates)
    return payload


def _policy(**updates):
    name = updates.get("name", "baseline")
    service = _service(f"checkout-{name}")
    values = {
        "name": name,
        "service": service,
        "environment": "production",
        "metric_type": ApmPolicy.MetricType.P95,
        "metric_window": 5,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "100"}],
        "trigger_after": 1,
        "recover_after": 2,
        "compare_mode": ApmPolicy.CompareMode.BASELINE_DAYS,
        "compare_offset_amount": 3,
        "compare_value_kind": ApmPolicy.CompareValueKind.DELTA,
    }
    values.update(updates)
    policy = ApmPolicy.objects.create(**values)
    bind_policy_organizations(policy)
    ApmPolicyNotificationTarget.objects.create(
        policy=policy,
        channel_id=7,
        channel_name="告警中心",
        channel_type="nats",
        delivery_mode="alert_event_copy",
        recipient_mode="none",
        recipients=[],
    )
    return policy


def _red(p95, requests=20):
    return ServiceRed(1, 0, p95, p95, request_count=requests)


class _DayStore:
    def __init__(self, by_end):
        self.by_end = by_end
        self.queries = []

    def service_red(self, query):
        self.queries.append(query)
        return self.by_end[query.ended_at]


@pytest.mark.parametrize(
    ("updates", "field"),
    [
        ({"compare_mode": "baseline_days", "compare_offset_amount": 1, "compare_value_kind": "delta"}, "compare_offset_amount"),
        ({"compare_mode": "baseline_days", "compare_offset_amount": 8, "compare_value_kind": "percent"}, "compare_offset_amount"),
        ({"compare_mode": "baseline_days", "compare_offset_amount": 3, "compare_value_kind": ""}, "compare_value_kind"),
        (
            {
                "metric_type": "no_traffic",
                "thresholds": [{"severity": "error", "comparator": "lte", "value": "0"}],
                "compare_mode": "baseline_days",
                "compare_offset_amount": 3,
                "compare_value_kind": "percent",
            },
            "compare_mode",
        ),
    ],
)
def test_baseline_days_rejects_illegal_combinations(apm_api_client, updates, field):
    service = _service(f"reject-{field}-{updates['compare_offset_amount']}")
    response = apm_api_client.post("/api/v1/apm/policies/", _payload(service, **updates), format="json")

    assert response.status_code == 400
    assert field in response.data


def test_baseline_days_accepts_delta_and_percent_and_keeps_legacy_payload(apm_api_client):
    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(
            _service("accept-baseline"),
            compare_mode="baseline_days",
            compare_offset_amount=7,
            compare_value_kind="percent",
        ),
        format="json",
    )
    legacy = apm_api_client.post("/api/v1/apm/policies/", _payload(_service("legacy-baseline"), name="旧比较"), format="json")

    assert created.status_code == 201
    assert created.data["compare_mode"] == "baseline_days"
    assert created.data["compare_offset_amount"] == 7
    assert created.data["compare_value_kind"] == "percent"
    assert legacy.status_code == 201
    assert legacy.data["compare_mode"] == "absolute"
    assert legacy.data["compare_offset_amount"] is None


def test_baseline_days_averages_half_open_windows_and_draws_the_mean_line():
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    window_end = evaluated_at
    current_start = window_end - timedelta(minutes=5)
    by_end = {window_end: _red(400)}
    for day, p95 in ((1, 100), (2, 200), (3, 300)):
        by_end[window_end - timedelta(days=day)] = _red(p95)
    store = _DayStore(by_end)
    policy = _policy(name="mean")
    result = DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).test_query(policy, evaluated_at=evaluated_at)

    assert [(query.started_at, query.ended_at) for query in store.queries] == [
        (current_start, window_end),
        (current_start - timedelta(days=1), window_end - timedelta(days=1)),
        (current_start - timedelta(days=2), window_end - timedelta(days=2)),
        (current_start - timedelta(days=3), window_end - timedelta(days=3)),
    ]
    assert result.data_state == MetricDataState.AVAILABLE
    assert result.baseline_value == Decimal("200")
    assert result.value == Decimal("200")
    assert result.baseline_days_used == 3
    assert [point.timestamp for point in result.baseline_series] == [current_start, window_end]
    assert [point.p95_ms for point in result.baseline_series] == [200.0, 200.0]


def test_baseline_days_below_half_the_days_is_missing_baseline():
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    window_end = evaluated_at
    by_end = {
        window_end: _red(400),
        window_end - timedelta(days=1): _red(100, requests=20),
        window_end - timedelta(days=2): _red(200, requests=5),
        window_end - timedelta(days=3): _red(300, requests=0),
    }
    policy = _policy(name="short", min_request_count=10)
    result = DjangoApmPolicyService(_DayStore(by_end), InMemoryNotificationDispatcher()).test_query(policy, evaluated_at=evaluated_at)

    assert result.data_state == MetricDataState.MISSING_BASELINE
    assert result.reason == "baseline_days_insufficient"
    assert result.baseline_days_used == 1
    assert result.breached is None


def test_baseline_days_fallback_uses_per_day_queries_and_logs_one_warning_without_the_query(caplog):
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    window_end = evaluated_at

    class FailingStore(_DayStore):
        def service_red_by_day(self, query, windows):
            query_text = "QUERY_" + "SENTINEL"
            response_text = "RESPONSE_" + "SENTINEL"
            raise RuntimeError(f"query {query_text} body {response_text}")

        def service_red(self, query):
            if query.ended_at != window_end:
                query_text = "QUERY_" + "SENTINEL"
                response_text = "RESPONSE_" + "SENTINEL"
                raise RuntimeError(f"query {query_text} body {response_text}")
            return super().service_red(query)

    policy = _policy(name="fallback-log")
    service = DjangoApmPolicyService(FailingStore({window_end: _red(400)}), InMemoryNotificationDispatcher())
    caplog.set_level(logging.DEBUG, logger="apm")

    with pytest.raises(TelemetryStoreUnavailable):
        service.test_query(policy, evaluated_at=evaluated_at)

    warnings = [record for record in caplog.records if record.name == "apm" and record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].msg == "event=apm_policy_baseline_failed policy_id=%s failed_stage=%s error_type=%s"
    assert warnings[0].args[1:] == ("baseline", "RuntimeError")
    rendered = logging.Formatter().format(warnings[0])
    assert "QUERY_SENTINEL" not in rendered
    assert "RESPONSE_SENTINEL" not in rendered


def test_baseline_days_fallback_still_averages_and_caps_targets_at_twenty():
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    window_end = evaluated_at
    by_end = {window_end: _red(400)}
    for day, p95 in ((1, 100), (2, 300)):
        by_end[window_end - timedelta(days=day)] = _red(p95)

    class FallbackStore(_DayStore):
        def __init__(self):
            super().__init__(by_end)
            self.grouped_calls = 0

        def service_red_by_day(self, query, windows):
            self.grouped_calls += 1
            raise RuntimeError("grouped failed")

    policy = _policy(name="cap", compare_offset_amount=2, endpoints=[f"/item-{index}" for index in range(21)])
    store = FallbackStore()
    DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=evaluated_at)

    assert store.grouped_calls == 1
    assert ApmPolicyTargetState.objects.filter(policy=policy).count() == 20
    state = ApmPolicyTargetState.objects.filter(policy=policy).first()
    assert state.consecutive_hits == 0
    alert = state.alert if hasattr(state, "alert") else None
    assert alert is None or state.status == ApmPolicyTargetState.Status.ACTIVE
