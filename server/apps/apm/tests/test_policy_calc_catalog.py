from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.models import ApmAlert, ApmAlertOutbox, ApmPolicy, ApmPolicyNotificationTarget, ApmService, ApmServiceOrganization
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import MetricDataState, ServiceRed, ServiceRedPoint
from apps.apm.tests.helpers import bind_policy_organizations

pytestmark = pytest.mark.django_db


def _service(name="checkout-catalog"):
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
        "name": "目录指标",
        "service_id": str(service.id),
        "organizations": [10],
        "environment": "production",
        "endpoints": [],
        "version_mode": "all",
        "versions": [],
        "metric_type": "p95",
        "evaluation_interval": 1,
        "metric_window": 5,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "500"}],
        "trigger_after": 1,
        "recover_after": 3,
        "notification_targets": [],
    }
    payload.update(updates)
    return payload


class _Store:
    def __init__(self, red: ServiceRed):
        self.red = red
        self.queries = []

    def service_red(self, query):
        self.queries.append(query)
        return self.red


def _policy(**updates):
    service = _service(name=f"checkout-{updates.get('metric_type', 'p95')}-{updates.get('name', 'catalog')}")
    values = {
        "name": "目录指标",
        "service": service,
        "environment": "production",
        "metric_type": ApmPolicy.MetricType.P95,
        "metric_window": 5,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "100"}],
        "trigger_after": 1,
        "recover_after": 3,
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


@pytest.mark.parametrize(
    ("updates", "field"),
    [
        ({"metric_type": "slow_request_count", "thresholds": [{"severity": "error", "comparator": "gte", "value": "50"}]}, "slow_threshold_ms"),
        (
            {"metric_type": "slow_request_rate", "slow_threshold_ms": 0, "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.1"}]},
            "slow_threshold_ms",
        ),
        (
            {
                "metric_type": "slow_request_rate",
                "slow_threshold_ms": 600001,
                "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.1"}],
            },
            "slow_threshold_ms",
        ),
        ({"metric_type": "p95", "slow_threshold_ms": 1000}, "slow_threshold_ms"),
        ({"metric_type": "apdex", "thresholds": [{"severity": "error", "comparator": "lt", "value": "0.8"}]}, "apdex_threshold_ms"),
        (
            {"metric_type": "apdex", "apdex_threshold_ms": 0, "thresholds": [{"severity": "error", "comparator": "lt", "value": "0.8"}]},
            "apdex_threshold_ms",
        ),
        ({"metric_type": "error_rate", "apdex_threshold_ms": 500}, "apdex_threshold_ms"),
        (
            {"metric_type": "apdex", "apdex_threshold_ms": 500, "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.8"}]},
            "thresholds",
        ),
        (
            {"metric_type": "apdex", "apdex_threshold_ms": 500, "thresholds": [{"severity": "error", "comparator": "gte", "value": "0.8"}]},
            "thresholds",
        ),
        (
            {"metric_type": "error_count", "min_request_count": 20, "thresholds": [{"severity": "error", "comparator": "gte", "value": "100"}]},
            "min_request_count",
        ),
        (
            {
                "metric_type": "slow_request_count",
                "slow_threshold_ms": 1000,
                "min_request_count": 20,
                "thresholds": [{"severity": "error", "comparator": "gte", "value": "50"}],
            },
            "min_request_count",
        ),
        (
            {"metric_type": "throughput", "min_request_count": 20, "thresholds": [{"severity": "error", "comparator": "gt", "value": "10"}]},
            "min_request_count",
        ),
        (
            {"metric_type": "no_traffic", "slow_threshold_ms": 1000, "thresholds": [{"severity": "error", "comparator": "lte", "value": "0"}]},
            "slow_threshold_ms",
        ),
        (
            {"metric_type": "no_traffic", "apdex_threshold_ms": 500, "thresholds": [{"severity": "error", "comparator": "lte", "value": "0"}]},
            "apdex_threshold_ms",
        ),
    ],
)
def test_metric_catalog_rejects_illegal_parameters(apm_api_client, updates, field):
    response = apm_api_client.post("/api/v1/apm/policies/", _payload(_service(), **updates), format="json")

    assert response.status_code == 400
    assert field in response.data


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({}, {"metric_type": "p95", "slow_threshold_ms": None, "apdex_threshold_ms": None}),
        (
            {"metric_type": "p99", "min_request_count": 20, "thresholds": [{"severity": "error", "comparator": "gt", "value": "800"}]},
            {"metric_type": "p99", "min_request_count": 20, "slow_threshold_ms": None},
        ),
        (
            {
                "metric_type": "slow_request_count",
                "slow_threshold_ms": 1000,
                "aggregation": "max",
                "thresholds": [{"severity": "error", "comparator": "gte", "value": "50"}],
            },
            {
                "metric_type": "slow_request_count",
                "slow_threshold_ms": 1000,
                "apdex_threshold_ms": None,
                "min_request_count": None,
            },
        ),
        (
            {
                "metric_type": "slow_request_rate",
                "slow_threshold_ms": 1000,
                "min_request_count": 20,
                "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.1"}],
            },
            {"metric_type": "slow_request_rate", "slow_threshold_ms": 1000, "min_request_count": 20},
        ),
        (
            {"metric_type": "apdex", "apdex_threshold_ms": 500, "thresholds": [{"severity": "error", "comparator": "lt", "value": "0.8"}]},
            {"metric_type": "apdex", "apdex_threshold_ms": 500, "slow_threshold_ms": None},
        ),
        (
            {"metric_type": "error_count", "aggregation": "max", "thresholds": [{"severity": "error", "comparator": "gte", "value": "100"}]},
            {"metric_type": "error_count", "min_request_count": None},
        ),
        (
            {"metric_type": "latency_avg", "min_request_count": 20, "thresholds": [{"severity": "error", "comparator": "gt", "value": "300"}]},
            {"metric_type": "latency_avg", "min_request_count": 20},
        ),
        (
            {"metric_type": "no_traffic", "thresholds": [{"severity": "error", "comparator": "lte", "value": "0"}]},
            {"metric_type": "no_traffic", "slow_threshold_ms": None, "apdex_threshold_ms": None, "compare_mode": "absolute"},
        ),
    ],
)
def test_metric_catalog_accepts_legal_parameters_and_keeps_legacy_payload(apm_api_client, updates, expected):
    created = apm_api_client.post("/api/v1/apm/policies/", _payload(_service(), **updates), format="json")

    assert created.status_code == 201
    assert "aggregation" not in created.data
    assert "no_data_after" not in created.data
    for key, value in expected.items():
        assert created.data[key] == value


def test_latency_error_count_and_apdex_use_red_fields(policy_factory=None):
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    point_low = ServiceRedPoint(timestamp=evaluated_at, request_rate=1, error_rate=0, p95_ms=10, p99_ms=20, p50_ms=100, avg_ms=80, max_ms=400)
    point_high = ServiceRedPoint(timestamp=evaluated_at, request_rate=1, error_rate=0, p95_ms=10, p99_ms=20, p50_ms=300, avg_ms=120, max_ms=900)
    series = (point_low, point_high)
    cases = [
        (ApmPolicy.MetricType.P50, ServiceRed(1, 0, 10, 20, timeseries=series, p50_ms=999), Decimal("999")),
        (ApmPolicy.MetricType.P75, ServiceRed(1, 0, 10, 20, p75_ms=180), Decimal("180")),
        (ApmPolicy.MetricType.P90, ServiceRed(1, 0, 10, 20, p90_ms=240), Decimal("240")),
        (ApmPolicy.MetricType.LATENCY_AVG, ServiceRed(1, 0, 10, 20, timeseries=series, avg_ms=999), Decimal("999")),
        (ApmPolicy.MetricType.LATENCY_MAX, ServiceRed(1, 0, 10, 20, timeseries=series, max_ms=1), Decimal("1")),
        (
            ApmPolicy.MetricType.ERROR_COUNT,
            ServiceRed(
                1,
                0,
                10,
                20,
                timeseries=(ServiceRedPoint(timestamp=evaluated_at, request_rate=1, error_rate=0, p95_ms=1, p99_ms=1, error_count=1),),
                error_count=9,
                request_count=20,
            ),
            Decimal("9"),
        ),
        (ApmPolicy.MetricType.SLOW_REQUEST_COUNT, ServiceRed(1, 0, 10, 20, slow_count=4, request_count=20), Decimal("4")),
        (ApmPolicy.MetricType.SLOW_REQUEST_RATE, ServiceRed(1, 0, 10, 20, slow_count=2, request_count=8), Decimal("0.25")),
        (ApmPolicy.MetricType.APDEX, ServiceRed(1, 0, 10, 20, satisfied_count=8, tolerating_count=2, request_count=10), Decimal("0.9")),
    ]
    for metric, red, expected in cases:
        updates = {
            "metric_type": metric,
            "thresholds": [{"severity": "error", "comparator": "gt", "value": "0"}],
        }
        if metric == ApmPolicy.MetricType.APDEX:
            updates["thresholds"] = [{"severity": "error", "comparator": "lt", "value": "1"}]
            updates["apdex_threshold_ms"] = 500
        if metric in ApmPolicy.SLOW_METRIC_TYPES:
            updates["slow_threshold_ms"] = 1000
            updates["thresholds"] = [{"severity": "error", "comparator": "gte", "value": "0"}]
        policy = _policy(**updates)
        store = _Store(red)
        result = DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).test_query(policy, evaluated_at=evaluated_at)
        assert result.value == expected
        assert result.data_state == MetricDataState.AVAILABLE
        assert store.queries[0].slow_threshold_ms == updates.get("slow_threshold_ms")
        assert store.queries[0].apdex_threshold_ms == updates.get("apdex_threshold_ms")


def test_absolute_window_matches_the_pre_delay_window_when_delay_is_zero():
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy = _policy()
    store = _Store(ServiceRed(3, 0, 450, 700, request_count=20))
    result = DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).test_query(policy, evaluated_at=evaluated_at)

    assert store.queries[0].started_at == evaluated_at - timedelta(minutes=5)
    assert store.queries[0].ended_at == evaluated_at
    assert result.value == Decimal("450")
    assert result.window_ended_at == evaluated_at
    assert result.breached is True


def test_evaluation_delay_shifts_both_windows_and_keeps_the_cursor_on_t(monkeypatch):
    monkeypatch.setenv("APM_POLICY_EVALUATION_DELAY", "60s")
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy = _policy(compare_mode=ApmPolicy.CompareMode.PREVIOUS_WINDOW, compare_value_kind=ApmPolicy.CompareValueKind.PERCENT)
    policy.thresholds = [{"severity": "error", "comparator": "gt", "value": "10"}]
    policy.save()
    current = ServiceRed(20, 0, 150, 200, request_count=40)
    baseline = ServiceRed(20, 0, 100, 150, request_count=40)
    store = _PairStore(current, baseline)
    service = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())

    service.evaluate(policy.id, evaluated_at=evaluated_at)

    delay = timedelta(seconds=60)
    assert store.queries[0].started_at == evaluated_at - delay - timedelta(minutes=5)
    assert store.queries[0].ended_at == evaluated_at - delay
    assert store.queries[1].started_at == evaluated_at - delay - timedelta(minutes=10)
    assert store.queries[1].ended_at == evaluated_at - delay - timedelta(minutes=5)
    state = policy.target_states.get()
    assert state.evaluation_cursor == evaluated_at.isoformat()
    alert = ApmAlert.objects.get()
    assert alert.started_at == evaluated_at
    point = alert.metric_snapshot.snapshots[-1]
    assert point["snapshot_time"] == (evaluated_at - delay).isoformat()
    event = alert.events.get()
    assert event.occurred_at == evaluated_at
    assert event.snapshot.policy_snapshot["slow_threshold_ms"] is None
    assert event.snapshot.policy_snapshot["apdex_threshold_ms"] is None
    assert ApmAlertOutbox.objects.get().payload["labels"]["metric_type"] == "p95"


def test_default_evaluation_delay_is_sixty_seconds(monkeypatch):
    monkeypatch.delenv("APM_POLICY_EVALUATION_DELAY", raising=False)
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy = _policy()
    store = _Store(ServiceRed(3, 0, 450, 700, request_count=20))
    DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).test_query(policy, evaluated_at=evaluated_at)

    assert store.queries[0].ended_at == evaluated_at - timedelta(seconds=60)
    assert store.queries[0].started_at == evaluated_at - timedelta(seconds=60) - timedelta(minutes=5)


def test_snapshot_and_dry_run_echo_slow_and_apdex_parameters():
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy = _policy(
        metric_type=ApmPolicy.MetricType.APDEX,
        apdex_threshold_ms=500,
        thresholds=[{"severity": "error", "comparator": "lt", "value": "0.8"}],
    )
    red = ServiceRed(1, 0, 10, 20, satisfied_count=1, tolerating_count=0, request_count=10)
    service = DjangoApmPolicyService(_Store(red), InMemoryNotificationDispatcher())

    preview = service.dry_run(policy, evaluated_at=evaluated_at)
    assert preview["apdex_threshold_ms"] == 500
    assert preview["slow_threshold_ms"] is None
    assert preview["items"][0]["current_value"] == "0.1"

    service.evaluate(policy.id, evaluated_at=evaluated_at)
    snapshot = ApmAlert.objects.get().events.get().snapshot
    assert snapshot.policy_snapshot["apdex_threshold_ms"] == 500
    assert snapshot.policy_snapshot["metric_type"] == "apdex"
    assert ApmAlertOutbox.objects.get().payload["labels"]["metric_type"] == "apdex"


def _noisy_points(evaluated_at, *, p95_ms):
    return tuple(
        ServiceRedPoint(
            timestamp=evaluated_at,
            request_rate=1,
            error_rate=0 if index < 19 else 1,
            p95_ms=p95_ms + 1000 + index,
            p99_ms=p95_ms + 2000,
            avg_ms=1,
            request_count=3,
            error_count=0 if index < 19 else 1,
        )
        for index in range(20)
    )


def test_non_count_metrics_use_the_whole_window_value():
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    whole_error_rate = Decimal("0.017241")
    current = ServiceRed(
        0.2,
        float(whole_error_rate),
        300,
        800,
        timeseries=_noisy_points(evaluated_at, p95_ms=300),
        request_count=58,
        error_count=1,
        avg_ms=40,
        max_ms=900,
        p50_ms=20,
        slow_count=2,
        satisfied_count=50,
        tolerating_count=6,
    )
    baseline = ServiceRed(
        0.1,
        0.01,
        100,
        200,
        timeseries=_noisy_points(evaluated_at, p95_ms=100),
        request_count=40,
        error_count=1,
        slow_count=1,
        satisfied_count=30,
        tolerating_count=4,
    )
    cases = [
        (
            ApmPolicy.MetricType.ERROR_RATE,
            Decimal(str(current.error_rate)),
            {"thresholds": [{"severity": "error", "comparator": "gt", "value": "0.01"}]},
        ),
        (ApmPolicy.MetricType.P95, Decimal("300"), {}),
        (
            ApmPolicy.MetricType.APDEX,
            Decimal("0.913793"),
            {"apdex_threshold_ms": 500, "thresholds": [{"severity": "error", "comparator": "lt", "value": "1"}]},
        ),
        (
            ApmPolicy.MetricType.SLOW_REQUEST_RATE,
            Decimal("0.034483"),
            {"slow_threshold_ms": 1000, "thresholds": [{"severity": "error", "comparator": "gt", "value": "0"}]},
        ),
        (ApmPolicy.MetricType.THROUGHPUT, Decimal("0.2"), {"thresholds": [{"severity": "error", "comparator": "gt", "value": "0"}]}),
    ]
    for metric, expected, extra in cases:
        policy = _policy(metric_type=metric, **extra)
        result = DjangoApmPolicyService(_Store(current), InMemoryNotificationDispatcher()).test_query(policy, evaluated_at=evaluated_at)
        assert result.current_value == expected
        assert result.current_value != Decimal("0.05")

    compared = _policy(
        name="previous-window",
        compare_mode=ApmPolicy.CompareMode.PREVIOUS_WINDOW,
        compare_value_kind=ApmPolicy.CompareValueKind.DELTA,
        thresholds=[{"severity": "error", "comparator": "gt", "value": "100"}],
    )
    paired = DjangoApmPolicyService(_PairStore(current, baseline), InMemoryNotificationDispatcher()).test_query(
        compared,
        evaluated_at=evaluated_at,
    )
    assert paired.current_value == Decimal("300")
    assert paired.baseline_value == Decimal("100")
    assert paired.value == Decimal("200")

    offset = _policy(
        name="offset-days",
        compare_mode=ApmPolicy.CompareMode.OFFSET_DAYS,
        compare_offset_amount=1,
        compare_value_kind=ApmPolicy.CompareValueKind.DELTA,
        thresholds=[{"severity": "error", "comparator": "gt", "value": "100"}],
    )
    offset_result = DjangoApmPolicyService(_PairStore(current, baseline), InMemoryNotificationDispatcher()).test_query(
        offset,
        evaluated_at=evaluated_at,
    )
    assert offset_result.current_value == Decimal("300")
    assert offset_result.baseline_value == Decimal("100")
    assert offset_result.value == Decimal("200")
    assert offset_result.result_unit == "ms"
    assert offset_result.breached is True


class _PairStore:
    def __init__(self, current: ServiceRed, baseline: ServiceRed):
        self._rows = (current, baseline)
        self.queries = []

    def service_red(self, query):
        self.queries.append(query)
        return self._rows[len(self.queries) - 1]
