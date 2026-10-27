from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.models import (
    ApmAlert,
    ApmAlertOutbox,
    ApmEvent,
    ApmPolicy,
    ApmPolicyNotificationTarget,
    ApmPolicyTargetState,
    ApmService,
    ApmServiceOrganization,
)
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import MetricDataState, NotificationDeliveryResult, ServiceRed, ServiceRedPoint
from apps.apm.tests.helpers import bind_policy_organizations

pytestmark = pytest.mark.django_db


class MutableMetricStore:
    def __init__(self, red: ServiceRed):
        self.red = red
        self.error = None
        self.queries = []

    def service_red(self, query):
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.red


class RetryableFailingDispatcher:
    def dispatch(self, delivery):
        return NotificationDeliveryResult(False, "provider_unavailable", True, "temporarily down")


class TerminalFailingDispatcher:
    def dispatch(self, delivery):
        return NotificationDeliveryResult(False, "channel_not_found", False, "deleted")


@pytest.fixture
def policy():
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name="checkout",
        normalized_name="checkout",
        first_seen_at=now,
        last_seen_at=now,
    )
    ApmServiceOrganization.objects.create(service=service, organization=10)
    policy = ApmPolicy.objects.create(
        name="生产错误率",
        service=service,
        environment="production",
        metric_type=ApmPolicy.MetricType.ERROR_RATE,
        thresholds=[{"severity": "error", "comparator": "gt", "value": "0.050000"}],
        trigger_after=2,
        recover_after=2,
    )
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


def test_evaluation_creates_one_idempotent_trigger_and_one_recovery(policy):
    metric_store = MutableMetricStore(ServiceRed(20, 0.10, 100, 150))
    dispatcher = InMemoryNotificationDispatcher()
    service = DjangoApmPolicyService(metric_store, dispatcher)
    started_at = timezone.now().replace(second=0, microsecond=0)

    service.evaluate(policy.id, evaluated_at=started_at)
    service.evaluate(policy.id, evaluated_at=started_at + timedelta(minutes=1))
    service.evaluate(policy.id, evaluated_at=started_at + timedelta(minutes=1))

    state = ApmPolicyTargetState.objects.get(policy=policy)
    assert state.status == ApmPolicyTargetState.Status.ACTIVE
    assert state.consecutive_hits == 0
    assert ApmAlert.objects.filter(status=ApmAlert.Status.ACTIVE).count() == 1
    assert ApmEvent.objects.filter(action=ApmEvent.Action.TRIGGERED).count() == 1
    assert len(ApmAlert.objects.get().metric_snapshot.snapshots) == 1
    assert ApmAlertOutbox.objects.count() == 1
    trigger = ApmAlertOutbox.objects.get()
    assert trigger.channel_id == 7
    assert trigger.recipients == []
    assert trigger.delivery_mode == "alert_event_copy"
    assert trigger.title == "APM 生产错误率触发"
    assert "shop/checkout" in trigger.body
    assert trigger.payload["action"] == "triggered"
    assert trigger.payload["organizations"] == [10]
    assert trigger.payload["external_id"] == state.active_alert_id

    metric_store.red = ServiceRed(20, 0.01, 100, 150)
    service.evaluate(policy.id, evaluated_at=started_at + timedelta(minutes=2))
    service.evaluate(policy.id, evaluated_at=started_at + timedelta(minutes=3))

    state.refresh_from_db()
    events = list(ApmAlertOutbox.objects.order_by("created_at"))
    alert = ApmAlert.objects.get()
    assert state.status == ApmPolicyTargetState.Status.NORMAL
    assert state.active_alert_id == ""
    assert alert.status == ApmAlert.Status.RECOVERED
    assert alert.events.count() == 2
    assert len(alert.metric_snapshot.snapshots) == 3
    assert [event.payload["action"] for event in events] == ["triggered", "recovered"]
    assert events[0].payload["external_id"] == events[1].payload["external_id"]

    result = service.retry_pending_events()
    assert result.accepted == 2
    assert result.failed == 0
    assert len(dispatcher.deliveries) == 2
    assert {delivery.channel_id for delivery in dispatcher.deliveries} == {7}
    assert not ApmAlertOutbox.objects.filter(delivery_status=ApmAlertOutbox.DeliveryStatus.PENDING).exists()


def test_mysql_outbox_portable_constraint_rejects_raw_queryset_duplicate(policy):
    from django.db import IntegrityError, connection, models, transaction

    if connection.vendor != "mysql":
        pytest.skip("MySQL 5.7 legacy data migration contract")

    service = DjangoApmPolicyService(MutableMetricStore(ServiceRed(20, 0.10, 100, 150)), InMemoryNotificationDispatcher())
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    service.evaluate(policy.id, evaluated_at=evaluated_at)
    service.evaluate(policy.id, evaluated_at=evaluated_at + timedelta(minutes=1))
    original = ApmAlertOutbox.objects.get()
    duplicate = ApmAlertOutbox(
        event_key=f"{original.event_key}:duplicate",
        event=original.event,
        channel_id=original.channel_id,
        payload={},
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        models.QuerySet(model=ApmAlertOutbox, using="default").bulk_create([duplicate])


def test_metric_failure_keeps_last_state_and_produces_no_event(policy):
    metric_store = MutableMetricStore(ServiceRed(20, 0.10, 100, 150))
    service = DjangoApmPolicyService(metric_store, InMemoryNotificationDispatcher())
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    service.evaluate(policy.id, evaluated_at=evaluated_at)
    before = ApmPolicyTargetState.objects.get(policy=policy)
    before_status = before.status
    before_hits = before.consecutive_hits
    before_cursor = before.evaluation_cursor
    metric_store.error = RuntimeError("victoriatraces unavailable")

    with pytest.raises(RuntimeError, match="victoriatraces unavailable"):
        service.evaluate(policy.id, evaluated_at=evaluated_at + timedelta(minutes=1))

    after = ApmPolicyTargetState.objects.get(policy=policy)
    assert after.status == before_status
    assert after.consecutive_hits == before_hits
    assert after.evaluation_cursor == before_cursor
    assert after.last_failed_at is not None
    assert ApmAlertOutbox.objects.count() == 0
    assert ApmEvent.objects.count() == 0


def test_firing_policy_does_not_recover_when_metric_window_has_no_samples(policy):
    policy.trigger_after = 1
    policy.recover_after = 1
    policy.save()
    metric_store = MutableMetricStore(ServiceRed(20, 0.10, 100, 150))
    service = DjangoApmPolicyService(metric_store, InMemoryNotificationDispatcher())
    evaluated_at = timezone.now().replace(second=0, microsecond=0)

    service.evaluate(policy.id, evaluated_at=evaluated_at)
    metric_store.red = ServiceRed(None, None, None, None)
    service.evaluate(policy.id, evaluated_at=evaluated_at + timedelta(minutes=1))

    state = ApmPolicyTargetState.objects.get(policy=policy)
    alert = ApmAlert.objects.get()
    assert state.status == ApmPolicyTargetState.Status.ACTIVE
    assert state.consecutive_recoveries == 0
    assert state.evaluation_cursor.endswith((evaluated_at + timedelta(minutes=1)).isoformat())
    assert alert.status == ApmAlert.Status.ACTIVE
    assert list(alert.events.values_list("action", flat=True)) == [ApmEvent.Action.TRIGGERED]


def test_failed_delivery_remains_pending_for_bounded_compensation(policy):
    metric_store = MutableMetricStore(ServiceRed(20, 0.10, 100, 150))
    evaluator = DjangoApmPolicyService(metric_store, InMemoryNotificationDispatcher())
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    evaluator.evaluate(policy.id, evaluated_at=evaluated_at)
    evaluator.evaluate(policy.id, evaluated_at=evaluated_at + timedelta(minutes=1))

    result = DjangoApmPolicyService(metric_store, RetryableFailingDispatcher()).retry_pending_events()

    outbox = ApmAlertOutbox.objects.get()
    assert result.failed == 1
    assert outbox.delivery_status == ApmAlertOutbox.DeliveryStatus.PENDING
    assert outbox.attempts == 1
    assert outbox.last_error_code == "provider_unavailable"
    assert outbox.next_retry_at is not None
    assert outbox.next_retry_at <= timezone.now() + timedelta(minutes=5, seconds=5)


def test_terminal_delivery_failure_does_not_retry_and_eight_retryable_failures_stop(policy):
    metric_store = MutableMetricStore(ServiceRed(20, 0.10, 100, 150))
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    evaluator = DjangoApmPolicyService(metric_store, InMemoryNotificationDispatcher())
    evaluator.evaluate(policy.id, evaluated_at=evaluated_at)
    evaluator.evaluate(policy.id, evaluated_at=evaluated_at + timedelta(minutes=1))
    outbox = ApmAlertOutbox.objects.get()

    DjangoApmPolicyService(metric_store, TerminalFailingDispatcher()).retry_pending_events()
    outbox.refresh_from_db()
    assert outbox.delivery_status == ApmAlertOutbox.DeliveryStatus.FAILED
    assert outbox.attempts == 1
    assert outbox.failed_at is not None
    assert outbox.next_retry_at is None

    outbox.delivery_status = ApmAlertOutbox.DeliveryStatus.PENDING
    outbox.attempts = 7
    outbox.next_retry_at = None
    outbox.failed_at = None
    outbox.save()
    DjangoApmPolicyService(metric_store, RetryableFailingDispatcher()).retry_pending_events()
    outbox.refresh_from_db()
    assert outbox.delivery_status == ApmAlertOutbox.DeliveryStatus.FAILED
    assert outbox.attempts == 8
    assert outbox.failed_at is not None


@pytest.mark.parametrize(
    ("metric_type", "red", "expected"),
    [
        (ApmPolicy.MetricType.P95, ServiceRed(3, 0, 450, 700), 450),
        (ApmPolicy.MetricType.P99, ServiceRed(3, 0, 450, 700), 700),
        (ApmPolicy.MetricType.THROUGHPUT, ServiceRed(3, 0, 450, 700), 3),
        (ApmPolicy.MetricType.NO_TRAFFIC, ServiceRed(0, 0, 450, 700), 0),
    ],
)
def test_policy_metric_types_use_controlled_red_values(policy, metric_type, red, expected):
    policy.metric_type = metric_type
    policy.thresholds = [{"severity": "error", "comparator": "lte", "value": str(expected)}]
    policy.metric_window = 1
    policy.save()
    metric_store = MutableMetricStore(red)
    service = DjangoApmPolicyService(metric_store, InMemoryNotificationDispatcher())

    result = service.test_query(policy, evaluated_at=timezone.now())

    assert result.value == expected
    assert result.breached is True
    assert metric_store.queries[-1].include_breakdown is True


def test_no_traffic_policy_treats_missing_request_samples_as_zero(policy):
    policy.metric_type = ApmPolicy.MetricType.NO_TRAFFIC
    policy.thresholds = [{"severity": "error", "comparator": "lte", "value": "0"}]
    policy.metric_window = 1
    policy.save()
    service = DjangoApmPolicyService(
        MutableMetricStore(ServiceRed(None, None, None, None)),
        InMemoryNotificationDispatcher(),
    )

    result = service.test_query(policy, evaluated_at=timezone.now())

    assert result.value == 0
    assert result.breached is True
    assert result.data_state == MetricDataState.AVAILABLE


def test_targets_keep_legal_cartesian_product_and_cap_oversized_combinations(policy):
    policy.version_mode = ApmPolicy.VersionMode.SPECIFIC
    policy.endpoints = [f"GET /e{i}" for i in range(10)]
    policy.versions = [f"v{i}" for i in range(10)]

    legal = DjangoApmPolicyService._targets(policy)

    assert len(legal) == 100
    assert legal[0] == ("GET /e0", "v0")
    assert legal[-1] == ("GET /e9", "v9")

    policy.endpoints = ["GET /a", "GET /b"]
    policy.versions = [f"v{i}" for i in range(100)]
    oversized = DjangoApmPolicyService._targets(policy)

    assert len(oversized) == 100
    assert oversized == [(endpoint, version) for endpoint in policy.endpoints for version in policy.versions][:100]


class ScriptedMetricStore:
    def __init__(self, reds):
        self.reds = list(reds)
        self.queries = []

    def service_red(self, query):
        self.queries.append(query)
        if len(self.reds) == 1:
            return self.reds[0]
        return self.reds.pop(0)


def _point(at, error_rate):
    return ServiceRedPoint(timestamp=at, request_rate=1, error_rate=error_rate, p95_ms=10, p99_ms=20)


def test_absolute_policy_queries_the_current_window_once_and_keeps_the_previous_result_shape(policy):
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy.metric_window = 5
    policy.save()
    store = ScriptedMetricStore([ServiceRed(20, 0.10, 100, 150, request_count=80)])
    result = DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).test_query(policy, evaluated_at=evaluated_at)

    assert len(store.queries) == 1
    assert store.queries[0].started_at == evaluated_at - timedelta(minutes=5)
    assert store.queries[0].ended_at == evaluated_at
    assert store.queries[0].include_breakdown is True
    assert store.queries[0].include_endpoints is True
    assert result.value == Decimal("0.1")
    assert result.current_value == result.value
    assert result.baseline_value is None
    assert result.baseline_series == ()
    assert result.breached is True
    assert result.data_state == MetricDataState.AVAILABLE
    assert result.series == ()
    assert result.threshold == {"severity": "error", "comparator": "gt", "value": "0.050000"}
    assert result.reason == ""


def test_previous_window_percent_and_delta_use_two_equal_windows(policy):
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy.metric_window = 5
    policy.compare_mode = ApmPolicy.CompareMode.PREVIOUS_WINDOW
    policy.compare_value_kind = ApmPolicy.CompareValueKind.PERCENT
    policy.thresholds = [{"severity": "error", "comparator": "gt", "value": "40"}]
    policy.save()
    baseline_point = _point(evaluated_at - timedelta(minutes=6), 0.04)
    current = ServiceRed(20, 0.06, 100, 150, request_count=318)
    baseline = ServiceRed(20, 0.04, 100, 150, timeseries=(baseline_point,), request_count=300)
    store = ScriptedMetricStore([current, baseline])

    result = DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).test_query(policy, evaluated_at=evaluated_at)

    assert store.queries[0].started_at == evaluated_at - timedelta(minutes=5)
    assert store.queries[0].ended_at == evaluated_at
    assert store.queries[1].started_at == evaluated_at - timedelta(minutes=10)
    assert store.queries[1].ended_at == evaluated_at - timedelta(minutes=5)
    assert store.queries[1].ended_at - store.queries[1].started_at == timedelta(minutes=5)
    assert store.queries[1].include_breakdown is True
    assert store.queries[1].include_endpoints is False
    assert result.value == Decimal("50")
    assert result.current_value == Decimal("0.06")
    assert result.baseline_value == Decimal("0.04")
    assert result.baseline_series == (baseline_point,)
    assert result.breached is True
    assert result.data_state == MetricDataState.AVAILABLE
    assert result.result_unit == "percent"

    policy.compare_value_kind = ApmPolicy.CompareValueKind.DELTA
    policy.thresholds = [{"severity": "error", "comparator": "gt", "value": "0.01"}]
    policy.save()
    delta = DjangoApmPolicyService(
        ScriptedMetricStore([current, baseline]),
        InMemoryNotificationDispatcher(),
    ).test_query(policy, evaluated_at=evaluated_at)
    assert delta.value == Decimal("0.02")
    assert delta.result_unit == "ratio"
    assert delta.breached is True


@pytest.mark.parametrize(
    ("mode", "offset"),
    [
        (ApmPolicy.CompareMode.OFFSET_1H, timedelta(hours=1)),
        (ApmPolicy.CompareMode.OFFSET_24H, timedelta(hours=24)),
    ],
)
def test_offset_windows_keep_the_metric_window_length(policy, mode, offset):
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy.metric_window = 5
    policy.compare_mode = mode
    policy.compare_value_kind = ApmPolicy.CompareValueKind.PERCENT
    policy.thresholds = [{"severity": "error", "comparator": "gt", "value": "10"}]
    policy.save()
    store = ScriptedMetricStore(
        [
            ServiceRed(20, 0.06, 100, 150, request_count=100),
            ServiceRed(20, 0.04, 100, 150, request_count=100),
        ]
    )
    DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).test_query(policy, evaluated_at=evaluated_at)

    assert store.queries[1].started_at == evaluated_at - timedelta(minutes=5) - offset
    assert store.queries[1].ended_at == evaluated_at - offset
    assert store.queries[1].ended_at - store.queries[1].started_at == timedelta(minutes=5)
    assert store.queries[1].include_endpoints is False


def test_percent_baseline_zero_is_missing_and_delta_baseline_zero_still_compares(policy):
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy.compare_mode = ApmPolicy.CompareMode.PREVIOUS_WINDOW
    policy.compare_value_kind = ApmPolicy.CompareValueKind.PERCENT
    policy.thresholds = [{"severity": "error", "comparator": "gt", "value": "10"}]
    policy.save()
    current = ServiceRed(20, 0.05, 100, 150, request_count=40)
    zero = ServiceRed(20, 0, 100, 150, request_count=40)
    percent = DjangoApmPolicyService(
        ScriptedMetricStore([current, zero]),
        InMemoryNotificationDispatcher(),
    ).test_query(policy, evaluated_at=evaluated_at)
    assert percent.data_state == MetricDataState.MISSING_BASELINE
    assert percent.reason == "baseline_zero"
    assert percent.value is None
    assert percent.breached is None

    policy.compare_value_kind = ApmPolicy.CompareValueKind.DELTA
    policy.thresholds = [{"severity": "error", "comparator": "gt", "value": "0.01"}]
    policy.save()
    delta = DjangoApmPolicyService(
        ScriptedMetricStore([current, zero]),
        InMemoryNotificationDispatcher(),
    ).test_query(policy, evaluated_at=evaluated_at)
    assert delta.data_state == MetricDataState.AVAILABLE
    assert delta.value == Decimal("0.05")
    assert delta.breached is True


def test_request_count_below_minimum_is_insufficient_without_a_baseline_query(policy):
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy.compare_mode = ApmPolicy.CompareMode.PREVIOUS_WINDOW
    policy.compare_value_kind = ApmPolicy.CompareValueKind.PERCENT
    policy.min_request_count = 20
    policy.thresholds = [{"severity": "error", "comparator": "gt", "value": "10"}]
    policy.save()
    store = ScriptedMetricStore([ServiceRed(20, 0.5, 100, 150, request_count=12)])

    result = DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).test_query(policy, evaluated_at=evaluated_at)

    assert len(store.queries) == 1
    assert result.data_state == MetricDataState.INSUFFICIENT_SAMPLES
    assert result.value is None
    assert result.current_value == Decimal("0.5")
    assert result.request_count == 12
    assert result.breached is None


def test_request_count_gate_applies_to_absolute_threshold_too(policy):
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    policy.compare_mode = ApmPolicy.CompareMode.ABSOLUTE
    policy.compare_value_kind = ""
    policy.min_request_count = 20
    policy.thresholds = [{"severity": "error", "comparator": "gt", "value": "0.1"}]
    policy.save()
    store = ScriptedMetricStore([ServiceRed(20, 0.5, 100, 150, request_count=12)])

    result = DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).test_query(policy, evaluated_at=evaluated_at)

    assert len(store.queries) == 1
    assert result.data_state == MetricDataState.INSUFFICIENT_SAMPLES
    assert result.value is None
    assert result.breached is None
    assert result.current_value == Decimal("0.5")

    policy.min_request_count = None
    policy.save()
    unlimited = DjangoApmPolicyService(
        ScriptedMetricStore([ServiceRed(20, 0.5, 100, 150, request_count=12)]),
        InMemoryNotificationDispatcher(),
    ).test_query(policy, evaluated_at=evaluated_at)
    assert unlimited.data_state == MetricDataState.AVAILABLE
    assert unlimited.breached is True


def test_missing_baseline_and_insufficient_samples_hold_state_and_advance_the_cursor(policy):
    policy.trigger_after = 1
    policy.recover_after = 1
    policy.save()
    store = ScriptedMetricStore([ServiceRed(20, 0.10, 100, 150, request_count=80)])
    service = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())
    started_at = timezone.now().replace(second=0, microsecond=0)
    service.evaluate(policy.id, evaluated_at=started_at)
    state = ApmPolicyTargetState.objects.get(policy=policy)
    state.consecutive_hits = 2
    state.consecutive_recoveries = 1
    state.consecutive_no_data = 4
    state.save()
    policy.compare_mode = ApmPolicy.CompareMode.PREVIOUS_WINDOW
    policy.compare_value_kind = ApmPolicy.CompareValueKind.PERCENT
    policy.thresholds = [{"severity": "error", "comparator": "gt", "value": "10"}]
    policy.save()
    store.reds = [
        ServiceRed(20, 0.06, 100, 150, request_count=80),
        ServiceRed(None, None, None, None),
    ]
    missing_at = started_at + timedelta(minutes=1)
    service.evaluate(policy.id, evaluated_at=missing_at)

    state.refresh_from_db()
    alert = ApmAlert.objects.get()
    assert state.consecutive_hits == 2
    assert state.consecutive_recoveries == 1
    assert state.consecutive_no_data == 4
    assert state.status == ApmPolicyTargetState.Status.ACTIVE
    assert state.active_alert_id
    assert state.evaluation_cursor.endswith(missing_at.isoformat())
    assert list(alert.events.values_list("action", flat=True)) == [ApmEvent.Action.TRIGGERED]
    assert alert.status == ApmAlert.Status.ACTIVE
    assert alert.metric_snapshot.snapshots[-1]["type"] == "info"
    assert alert.metric_snapshot.snapshots[-1]["data_state"] == "missing_baseline"

    policy.min_request_count = 20
    policy.save()
    store.reds = [ServiceRed(20, 0.5, 100, 150, request_count=12)]
    short_at = started_at + timedelta(minutes=2)
    service.evaluate(policy.id, evaluated_at=short_at)
    state.refresh_from_db()
    alert.refresh_from_db()
    assert state.consecutive_hits == 2
    assert state.consecutive_recoveries == 1
    assert state.consecutive_no_data == 4
    assert state.evaluation_cursor.endswith(short_at.isoformat())
    assert alert.events.count() == 1
    assert alert.status == ApmAlert.Status.ACTIVE
    assert alert.metric_snapshot.snapshots[-1]["data_state"] == "insufficient_samples"


def test_no_data_ignores_compare_mode_and_does_not_query_the_baseline(policy):
    policy.trigger_after = 1
    policy.recover_after = 1
    policy.save()
    store = ScriptedMetricStore([ServiceRed(20, 0.10, 100, 150, request_count=80)])
    service = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())
    started_at = timezone.now().replace(second=0, microsecond=0)
    service.evaluate(policy.id, evaluated_at=started_at)
    policy.compare_mode = ApmPolicy.CompareMode.PREVIOUS_WINDOW
    policy.compare_value_kind = ApmPolicy.CompareValueKind.PERCENT
    policy.save()
    store.reds = [ServiceRed(None, None, None, None)]
    quiet_at = started_at + timedelta(minutes=1)
    before = len(store.queries)
    service.evaluate(policy.id, evaluated_at=quiet_at)

    state = ApmPolicyTargetState.objects.get(policy=policy)
    assert len(store.queries) - before == 1
    assert state.consecutive_recoveries == 0
    assert state.consecutive_no_data == 1
    assert state.status == ApmPolicyTargetState.Status.ACTIVE
    assert ApmAlert.objects.get().status == ApmAlert.Status.ACTIVE
    assert list(ApmEvent.objects.values_list("action", flat=True)) == [ApmEvent.Action.TRIGGERED]
