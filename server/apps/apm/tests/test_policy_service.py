from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.models import (
    ApmAlert,
    ApmAlertOutbox,
    ApmEvent,
    ApmPolicy,
    ApmPolicyNotificationTarget,
    ApmPolicyState,
    ApmService,
    ApmServiceOrganization,
)
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import MetricDataState, NotificationDeliveryResult, ServiceRed


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
        comparator=ApmPolicy.Comparator.GREATER_THAN,
        threshold="0.050000",
        duration_window=2,
        recovery_window=2,
        severity=ApmPolicy.Severity.ERROR,
        notice=True,
        notice_type_ids=[7],
        notice_users=["on-call"],
    )
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

    state = ApmPolicyState.objects.get(policy=policy)
    assert state.status == ApmPolicyState.Status.FIRING
    assert state.consecutive_hits == 2
    assert ApmAlert.objects.filter(status=ApmAlert.Status.FIRING).count() == 1
    assert ApmEvent.objects.filter(action=ApmEvent.Action.CREATED).count() == 1
    assert ApmAlertOutbox.objects.count() == 1
    trigger = ApmAlertOutbox.objects.get()
    assert trigger.channel_id == 7
    assert trigger.recipients == []
    assert trigger.delivery_mode == "alert_event_copy"
    assert trigger.title == "APM 生产错误率触发"
    assert "shop/checkout" in trigger.body
    assert trigger.payload["action"] == "created"
    assert trigger.payload["organizations"] == [10]
    assert trigger.payload["external_id"] == state.external_alert_id

    metric_store.red = ServiceRed(20, 0.01, 100, 150)
    service.evaluate(policy.id, evaluated_at=started_at + timedelta(minutes=2))
    service.evaluate(policy.id, evaluated_at=started_at + timedelta(minutes=3))

    state.refresh_from_db()
    events = list(ApmAlertOutbox.objects.order_by("created_at"))
    alert = ApmAlert.objects.get()
    assert state.status == ApmPolicyState.Status.NORMAL
    assert state.external_alert_id == ""
    assert alert.status == ApmAlert.Status.RECOVERED
    assert alert.events.count() == 2
    assert [event.payload["action"] for event in events] == ["created", "recovery"]
    assert events[0].payload["external_id"] == events[1].payload["external_id"]

    result = service.retry_pending_events()
    assert result.accepted == 2
    assert result.failed == 0
    assert len(dispatcher.deliveries) == 2
    assert {delivery.channel_id for delivery in dispatcher.deliveries} == {7}
    assert not ApmAlertOutbox.objects.filter(
        delivery_status=ApmAlertOutbox.DeliveryStatus.PENDING
    ).exists()


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
    before = ApmPolicyState.objects.get(policy=policy)
    metric_store.error = RuntimeError("victoriatraces unavailable")

    with pytest.raises(RuntimeError, match="victoriatraces unavailable"):
        service.evaluate(policy.id, evaluated_at=evaluated_at + timedelta(minutes=1))

    after = ApmPolicyState.objects.get(policy=policy)
    assert after.status == before.status
    assert after.consecutive_hits == before.consecutive_hits
    assert after.evaluation_cursor == before.evaluation_cursor
    assert after.last_failed_at is not None
    assert ApmAlertOutbox.objects.count() == 0
    assert ApmEvent.objects.count() == 0


def test_firing_policy_does_not_recover_when_metric_window_has_no_samples(policy):
    policy.duration_window = 1
    policy.recovery_window = 1
    policy.save()
    metric_store = MutableMetricStore(ServiceRed(20, 0.10, 100, 150))
    service = DjangoApmPolicyService(metric_store, InMemoryNotificationDispatcher())
    evaluated_at = timezone.now().replace(second=0, microsecond=0)

    service.evaluate(policy.id, evaluated_at=evaluated_at)
    metric_store.red = ServiceRed(None, None, None, None)
    service.evaluate(policy.id, evaluated_at=evaluated_at + timedelta(minutes=1))

    state = ApmPolicyState.objects.get(policy=policy)
    alert = ApmAlert.objects.get()
    assert state.status == ApmPolicyState.Status.FIRING
    assert state.consecutive_recoveries == 0
    assert state.evaluation_cursor.endswith((evaluated_at + timedelta(minutes=1)).isoformat())
    assert alert.status == ApmAlert.Status.FIRING
    assert list(alert.events.values_list("action", flat=True)) == [ApmEvent.Action.CREATED]


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
    policy.comparator = ApmPolicy.Comparator.LESS_THAN_OR_EQUAL
    policy.threshold = expected
    policy.duration_window = 1
    policy.save()
    metric_store = MutableMetricStore(red)
    service = DjangoApmPolicyService(metric_store, InMemoryNotificationDispatcher())

    result = service.test_query(policy, evaluated_at=timezone.now())

    assert result.value == expected
    assert result.breached is True
    assert metric_store.queries[-1].include_breakdown is False


def test_no_traffic_policy_treats_missing_request_samples_as_zero(policy):
    policy.metric_type = ApmPolicy.MetricType.NO_TRAFFIC
    policy.comparator = ApmPolicy.Comparator.LESS_THAN_OR_EQUAL
    policy.threshold = 0
    policy.duration_window = 1
    policy.save()
    service = DjangoApmPolicyService(
        MutableMetricStore(ServiceRed(None, None, None, None)),
        InMemoryNotificationDispatcher(),
    )

    result = service.test_query(policy, evaluated_at=timezone.now())

    assert result.value == 0
    assert result.breached is True
    assert result.data_state == MetricDataState.AVAILABLE
