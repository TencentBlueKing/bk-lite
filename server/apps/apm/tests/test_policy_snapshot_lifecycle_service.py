from datetime import timedelta
import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
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
from apps.apm.services import ApmEventSnapshotStore, DjangoApmPolicyService
from apps.apm.services.contracts import ServiceRed, ServiceRedPoint

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def snapshot_object_storage(mocker):
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        return_value="apm/test-snapshot.json.gz",
    )


class MutableMetricStore:
    def __init__(self, red):
        self.red = red
        self.queries = []

    def service_red(self, query):
        self.queries.append(query)
        return self.red


@pytest.fixture
def multilevel_policy():
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
    return ApmPolicy.objects.create(
        name="结账错误率",
        alert_name="${service} 错误率超过 ${threshold}",
        service=service,
        environment="production",
        endpoints=["POST /checkout"],
        version_mode="specific",
        versions=["v2"],
        metric_type="error_rate",
        evaluation_interval=1,
        metric_window=5,
        aggregation="max",
        thresholds=[
            {"severity": "critical", "comparator": "gt", "value": "0.20"},
            {"severity": "error", "comparator": "gt", "value": "0.10"},
            {"severity": "warning", "comparator": "gt", "value": "0.05"},
        ],
        trigger_after=2,
        recover_after=2,
    )


def _red(at, value):
    return ServiceRed(
        request_rate=10,
        error_rate=value,
        p95_ms=120,
        p99_ms=180,
        timeseries=(ServiceRedPoint(at, 10, value, 120, 180),),
    )


def test_multilevel_lifecycle_creates_trigger_escalation_recovery_and_immutable_snapshots(multilevel_policy):
    started_at = timezone.now().replace(second=0, microsecond=0)
    metric_store = MutableMetricStore(_red(started_at, 0.12))
    evaluator = DjangoApmPolicyService(metric_store, InMemoryNotificationDispatcher())

    evaluator.evaluate(multilevel_policy.id, evaluated_at=started_at)
    evaluator.evaluate(multilevel_policy.id, evaluated_at=started_at + timedelta(minutes=1))
    metric_store.red = _red(started_at + timedelta(minutes=2), 0.25)
    evaluator.evaluate(multilevel_policy.id, evaluated_at=started_at + timedelta(minutes=2))
    evaluator.evaluate(multilevel_policy.id, evaluated_at=started_at + timedelta(minutes=3))
    metric_store.red = _red(started_at + timedelta(minutes=4), 0.01)
    evaluator.evaluate(multilevel_policy.id, evaluated_at=started_at + timedelta(minutes=4))
    evaluator.evaluate(multilevel_policy.id, evaluated_at=started_at + timedelta(minutes=5))

    alert = ApmAlert.objects.get()
    events = list(alert.events.order_by("occurred_at"))
    assert alert.status == ApmAlert.Status.RECOVERED
    assert alert.endpoint == "POST /checkout"
    assert alert.version == "v2"
    assert [event.action for event in events] == [
        ApmEvent.Action.TRIGGERED,
        ApmEvent.Action.ESCALATED,
        ApmEvent.Action.RECOVERED,
    ]
    assert [event.severity for event in events] == ["error", "critical", "critical"]
    assert ApmEventSnapshot.objects.filter(alert=alert).count() == 3
    metric_snapshot = alert.metric_snapshot
    assert ApmAlertMetricSnapshot.objects.filter(alert=alert).count() == 1
    assert [item["snapshot_time"] for item in metric_snapshot.snapshots] == [
        (started_at + timedelta(minutes=1)).isoformat(),
        (started_at + timedelta(minutes=2)).isoformat(),
        (started_at + timedelta(minutes=3)).isoformat(),
        (started_at + timedelta(minutes=4)).isoformat(),
        (started_at + timedelta(minutes=5)).isoformat(),
    ]
    assert [item["type"] for item in metric_snapshot.snapshots] == ["event", "info", "event", "info", "event"]
    assert [item["value"] for item in metric_snapshot.snapshots] == ["0.12", "0.25", "0.25", "0.01", "0.01"]
    assert [item["threshold"]["value"] for item in metric_snapshot.snapshots] == ["0.10", "0.20", "0.20", "0.20", "0.20"]
    assert [item["event_id"] for item in metric_snapshot.snapshots] == [
        events[0].event_id,
        None,
        events[1].event_id,
        None,
        events[2].event_id,
    ]
    for snapshot in ApmEventSnapshot.objects.filter(alert=alert):
        assert snapshot.payload_status == ApmEventSnapshot.PayloadStatus.PENDING
        ApmEventSnapshotStore.persist(snapshot.id)
    trigger_snapshot = events[0].snapshot
    trigger_snapshot.refresh_from_db()
    assert trigger_snapshot.schema_version == 1
    assert trigger_snapshot.policy_snapshot["thresholds"][1]["value"] == "0.10"
    assert trigger_snapshot.object_snapshot == {
        "service_id": str(multilevel_policy.service_id),
        "service_namespace": "shop",
        "service_name": "checkout",
        "endpoint": "POST /checkout",
        "environment": "production",
        "version": "v2",
    }
    assert trigger_snapshot.evaluation_snapshot["threshold"] == "0.10"
    assert trigger_snapshot.trace_context["endpoint"] == "POST /checkout"
    assert trigger_snapshot.pending_payload == {}
    assert trigger_snapshot.payload_status == ApmEventSnapshot.PayloadStatus.AVAILABLE
    assert metric_store.queries[-1].endpoint == "POST /checkout"
    assert metric_store.queries[-1].version == "v2"


def test_no_data_event_has_snapshot_and_does_not_fabricate_a_metric_value(multilevel_policy):
    multilevel_policy.trigger_after = 1
    multilevel_policy.no_data_after = 2
    multilevel_policy.no_data_severity = "critical"
    multilevel_policy.no_data_alert_name = "${service} 无数据告警"
    multilevel_policy.save()
    metric_store = MutableMetricStore(ServiceRed(None, None, None, None))
    evaluator = DjangoApmPolicyService(metric_store, InMemoryNotificationDispatcher())
    started_at = timezone.now().replace(second=0, microsecond=0)

    evaluator.evaluate(multilevel_policy.id, evaluated_at=started_at)
    evaluator.evaluate(multilevel_policy.id, evaluated_at=started_at + timedelta(minutes=1))

    event = ApmEvent.objects.get()
    state = ApmPolicyTargetState.objects.get(policy=multilevel_policy)
    assert event.action == ApmEvent.Action.TRIGGERED
    assert event.value is None
    assert event.snapshot.policy_snapshot["no_data_alert_name"] == "${service} 无数据告警"
    assert state.status == ApmPolicyTargetState.Status.ACTIVE
    assert event.snapshot.evaluation_snapshot["data_state"] == "no_data"
    assert event.snapshot.evaluation_snapshot["value"] is None
    evaluator.evaluate(multilevel_policy.id, evaluated_at=started_at + timedelta(minutes=2))
    metric_store.red = _red(started_at + timedelta(minutes=3), 0.01)
    evaluator.evaluate(multilevel_policy.id, evaluated_at=started_at + timedelta(minutes=3))
    evaluator.evaluate(multilevel_policy.id, evaluated_at=started_at + timedelta(minutes=4))

    metric_snapshots = event.alert.metric_snapshot.snapshots
    assert [item["type"] for item in metric_snapshots] == ["no_data", "no_data", "info", "event"]
    assert [item["data_state"] for item in metric_snapshots] == ["no_data", "no_data", "available", "available"]
    assert metric_snapshots[0]["threshold"]["comparator"] == "no_data"
    assert metric_snapshots[1]["threshold"] is None
    assert [item["threshold"]["comparator"] for item in metric_snapshots[2:]] == ["gt", "gt"]
    assert metric_snapshots[-1]["event_id"].endswith(":recovered:critical")


def test_snapshot_payload_failure_keeps_domain_event_and_retryable_evidence(multilevel_policy, mocker):
    multilevel_policy.trigger_after = 1
    multilevel_policy.save()
    at = timezone.now().replace(second=0, microsecond=0)
    metric_store = MutableMetricStore(_red(at, 0.12))
    upload = mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        side_effect=RuntimeError("minio unavailable"),
    )

    DjangoApmPolicyService(metric_store, InMemoryNotificationDispatcher()).evaluate(
        multilevel_policy.id,
        evaluated_at=at,
    )
    ApmEventSnapshotStore.persist(ApmEventSnapshot.objects.get().id)

    assert ApmAlert.objects.count() == 1
    assert ApmEvent.objects.count() == 1
    snapshot = ApmEventSnapshot.objects.get()
    assert snapshot.payload_status == ApmEventSnapshot.PayloadStatus.UNAVAILABLE
    assert snapshot.payload_error_code == "object_storage_unavailable"
    assert snapshot.pending_payload["series"]
    assert upload.call_count == 1
