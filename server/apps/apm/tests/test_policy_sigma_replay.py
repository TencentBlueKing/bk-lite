from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.adapters.victoriatraces import VictoriaTracesTelemetryStore
from apps.apm.models import (
    ApmAlert,
    ApmAlertMetricSnapshot,
    ApmEvent,
    ApmEventSnapshot,
    ApmPolicy,
    ApmPolicyTargetState,
    ApmService,
    ApmServiceOrganization,
)
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import MetricDataState, ServiceMetricQuery, ServiceRed
from apps.apm.services.policies import evaluation_delay
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
        "name": "标准差",
        "service_id": str(service.id),
        "organizations": [10],
        "environment": "production",
        "metric_type": "p95",
        "metric_window": 5,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "2"}],
        "trigger_after": 1,
        "recover_after": 1,
        "notification_targets": [],
        "compare_mode": "baseline_days",
        "compare_offset_amount": 7,
        "compare_value_kind": "sigma",
    }
    payload.update(updates)
    return payload


def _policy(**updates):
    service = _service(updates.pop("service_name", "sigma-checkout"))
    values = {
        "name": "sigma",
        "service": service,
        "environment": "production",
        "metric_type": ApmPolicy.MetricType.P95,
        "metric_window": 5,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "2"}],
        "trigger_after": 1,
        "recover_after": 1,
        "compare_mode": ApmPolicy.CompareMode.BASELINE_DAYS,
        "compare_offset_amount": 7,
        "compare_value_kind": ApmPolicy.CompareValueKind.SIGMA,
    }
    values.update(updates)
    policy = ApmPolicy.objects.create(**values)
    bind_policy_organizations(policy)
    return policy


def _red(p95, requests=20):
    return ServiceRed(1, 0, p95, p95, request_count=requests)


class _DayStore:
    def __init__(self, by_end):
        self.by_end = by_end

    def service_red(self, query):
        return self.by_end.get(query.ended_at, ServiceRed(None, None, None, None, request_count=0))


def test_sigma_hits_when_the_current_window_is_two_and_a_half_deviations_above_the_mean():
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    window_end = evaluated_at - evaluation_delay()
    by_end = {window_end: _red(125)}
    for day, p95 in enumerate((90, 90, 90, 100, 110, 110, 110), start=1):
        by_end[window_end - timedelta(days=day)] = _red(p95)
    result = DjangoApmPolicyService(_DayStore(by_end), InMemoryNotificationDispatcher()).test_query(
        _policy(),
        evaluated_at=evaluated_at,
    )

    assert result.data_state == MetricDataState.AVAILABLE
    assert result.value == Decimal("2.5")
    assert result.breached is True
    assert result.threshold["severity"] == "error"
    assert result.baseline_days_used == 7


def test_sigma_with_only_two_usable_days_is_missing_baseline():
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    window_end = evaluated_at - evaluation_delay()
    by_end = {window_end: _red(125)}
    by_end[window_end - timedelta(days=1)] = _red(100)
    by_end[window_end - timedelta(days=2)] = _red(110)
    result = DjangoApmPolicyService(_DayStore(by_end), InMemoryNotificationDispatcher()).test_query(
        _policy(compare_offset_amount=3, service_name="sigma-short"),
        evaluated_at=evaluated_at,
    )

    assert result.data_state == MetricDataState.MISSING_BASELINE
    assert result.breached is None
    assert result.baseline_days_used == 2


@pytest.mark.parametrize(
    ("updates", "field"),
    [
        ({"compare_mode": "previous_window", "compare_offset_amount": None, "compare_value_kind": "sigma"}, "compare_value_kind"),
        ({"compare_offset_amount": 2, "compare_value_kind": "sigma"}, "compare_value_kind"),
        ({"thresholds": [{"severity": "error", "comparator": "gt", "value": "6"}]}, "thresholds"),
        ({"thresholds": [{"severity": "error", "comparator": "gt", "value": "0.4"}]}, "thresholds"),
    ],
)
def test_sigma_rules_reject_the_wrong_baseline_and_out_of_range_k(apm_api_client, updates, field):
    response = apm_api_client.post("/api/v1/apm/policies/", _payload(_service(f"sigma-reject-{field}"), **updates), format="json")

    assert response.status_code == 400
    assert field in response.data


def test_sigma_accepts_three_day_baseline_and_boundary_k(apm_api_client):
    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(
            _service("sigma-ok"),
            compare_offset_amount=3,
            thresholds=[{"severity": "warning", "comparator": "gte", "value": "0.5"}],
        ),
        format="json",
    )

    assert created.status_code == 201
    assert created.data["compare_value_kind"] == "sigma"
    assert created.data["compare_offset_amount"] == 3


class _ReplayStore:
    def __init__(self):
        self.calls = []

    def service_red(self, query):
        self.calls.append("service_red")
        return ServiceRed(10, 0.01, 10, 10, request_count=30)

    def service_red_by_window(self, query, window_minutes):
        self.calls.append("series")
        step = timedelta(minutes=window_minutes)
        points = []
        end = query.ended_at
        index = 0
        while end > query.started_at:
            error_rate = 0.2 if index in {0, 3} else 0.01
            points.append((end, ServiceRed(10, error_rate, 10, 10, request_count=30)))
            end -= step
            index += 1
        return tuple(points)


def test_replay_counts_hits_without_writing_state_and_stays_within_the_query_budget():
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy = _policy(
        service_name="replay",
        metric_type=ApmPolicy.MetricType.ERROR_RATE,
        metric_window=60,
        compare_mode=ApmPolicy.CompareMode.ABSOLUTE,
        compare_value_kind="",
        compare_offset_amount=None,
        thresholds=[{"severity": "error", "comparator": "gt", "value": "0.05"}],
    )
    before = (
        ApmAlert.objects.count(),
        ApmEvent.objects.count(),
        ApmPolicyTargetState.objects.count(),
        ApmAlertMetricSnapshot.objects.count(),
        ApmEventSnapshot.objects.count(),
    )
    store = _ReplayStore()
    result = DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).dry_run(policy, evaluated_at=evaluated_at, replay_hours=24)
    after = (
        ApmAlert.objects.count(),
        ApmEvent.objects.count(),
        ApmPolicyTargetState.objects.count(),
        ApmAlertMetricSnapshot.objects.count(),
        ApmEventSnapshot.objects.count(),
    )

    replay = result["items"][0]["replay"]
    assert replay["windows"] == 24
    assert replay["hits"] == 2
    assert len(replay["hit_at"]) == 2
    assert before == after
    assert store.calls.count("series") == 1
    assert len(store.calls) <= 20 * (1 + 0) * 2


def test_replay_hours_outside_zero_and_twenty_four_is_rejected(apm_api_client):
    response = apm_api_client.post(
        "/api/v1/apm/policies/dry-run/",
        {**_payload(_service("replay-reject")), "replay_hours": 12},
        format="json",
    )

    assert response.status_code == 400
    assert "replay_hours" in response.data


def test_window_replay_query_groups_by_the_policy_window():
    store = VictoriaTracesTelemetryStore(endpoint="http://victoria-traces")
    captured = []

    def fake_stats(query, started_at, ended_at):
        captured.append(query)
        return [{"metric": {"__name__": "requests", "_time": "2026-10-28T08:00:00Z"}, "value": [1, "4"]}]

    store._stats = fake_stats
    started = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)
    points = store.service_red_by_window(
        ServiceMetricQuery(
            service_namespace="shop",
            service_name="demo-storefront",
            environment="production",
            started_at=started,
            ended_at=started + timedelta(hours=1),
        ),
        60,
    )

    assert "stats by (_time:60m)" in captured[0]
    assert points[0][0] == started + timedelta(hours=1)
    assert points[0][1].request_count == 4
