from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.models import ApmAlert, ApmEvent, ApmEventSnapshot, ApmEventSnapshotPayload, ApmPolicy, ApmService, ApmServiceOrganization
from apps.apm.services import ApmEventSnapshotStore, DjangoApmPolicyService
from apps.apm.services.contracts import MetricDataState, PolicyQueryResult, ServiceRed, ServiceRedPoint

pytestmark = pytest.mark.django_db


class MetricStore:
    def __init__(self, at):
        self.red = ServiceRed(10, 0.2, 100, 150, (ServiceRedPoint(at, 10, 0.2, 100, 150),))

    def service_red(self, query):
        return self.red


def _trigger(*, organization=10):
    at = timezone.now().replace(second=0, microsecond=0)
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name=f"checkout-{organization}",
        normalized_name=f"checkout-{organization}",
        first_seen_at=at,
        last_seen_at=at,
    )
    ApmServiceOrganization.objects.create(service=service, organization=organization)
    policy = ApmPolicy.objects.create(
        name="错误率",
        service=service,
        environment="production",
        endpoints=["POST /checkout"],
        metric_type="error_rate",
        thresholds=[{"severity": "error", "comparator": "gt", "value": "0.1"}],
        trigger_after=1,
        comparator="gt",
        threshold="0.1",
        duration_window=1,
        recovery_window=1,
        severity="error",
    )
    DjangoApmPolicyService(MetricStore(at), InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=at)
    return policy, ApmAlert.objects.get(policy=policy), at


def test_alert_and_snapshot_reads_are_organization_scoped(apm_api_client):
    _, visible, _ = _trigger(organization=10)
    _trigger(organization=20)

    listed = apm_api_client.get("/api/v1/apm/alerts/")
    visible_snapshots = apm_api_client.get(f"/api/v1/apm/alerts/{visible.id}/snapshots/")
    hidden = ApmAlert.objects.get(organizations=[20])
    hidden_snapshots = apm_api_client.get(f"/api/v1/apm/alerts/{hidden.id}/snapshots/")

    assert listed.status_code == 200
    assert [str(item["id"]) for item in listed.data] == [str(visible.id)]
    assert visible_snapshots.status_code == 200
    assert visible_snapshots.data[0]["payload_status"] == "pending"
    assert hidden_snapshots.status_code == 404


def test_manual_close_appends_canonical_event_and_snapshot(apm_api_client):
    _, alert, _ = _trigger()

    response = apm_api_client.post(f"/api/v1/apm/alerts/{alert.id}/close/")

    assert response.status_code == 200
    assert response.data["status"] == "closed"
    assert [event["action"] for event in response.data["events"]] == ["triggered", "closed"]
    assert list(alert.snapshots.order_by("occurred_at").values_list("action", flat=True)) == ["triggered", "closed"]
    assert ApmEvent.objects.filter(alert=alert, action=ApmEvent.Action.CLOSED).count() == 1


def test_close_requires_operate_permission(apm_user):
    _, alert, _ = _trigger()
    apm_user.permission["apm"] = {"events-View"}
    client = APIClient()
    client.force_authenticate(user=apm_user)
    client.cookies["current_team"] = "10"

    response = client.post(f"/api/v1/apm/alerts/{alert.id}/close/")

    assert response.status_code == 403
    alert.refresh_from_db()
    assert alert.status == ApmAlert.Status.ACTIVE


def test_policy_delete_does_not_change_or_remove_historical_snapshot():
    policy, alert, _ = _trigger()
    before = dict(alert.snapshots.get().policy_snapshot)

    policy.delete()
    alert.refresh_from_db()

    assert alert.policy is None
    assert alert.snapshots.get().policy_snapshot == before


def test_event_id_is_idempotent_and_retention_clears_available_or_failed_payload(mocker):
    policy, alert, at = _trigger()
    event = alert.events.get()
    existing = event.snapshot
    result = PolicyQueryResult(
        value=event.value,
        breached=True,
        evaluated_at=at,
        data_state=MetricDataState.AVAILABLE,
        series=(ServiceRedPoint(at, 10, 0.2, 100, 150),),
        threshold={"severity": "error", "comparator": "gt", "value": "0.1"},
    )

    duplicate = ApmEventSnapshotStore.stage(
        event=event,
        policy=policy,
        result=result,
        endpoint="POST /checkout",
        version="",
        threshold=result.threshold,
    )
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        return_value="apm/snapshot.json.gz",
    )
    ApmEventSnapshotStore.persist(existing.id)
    existing.refresh_from_db()
    existing.retention_expires_at = at - timedelta(seconds=1)
    existing.save(update_fields=("retention_expires_at", "updated_at"))
    delete_payload = mocker.patch.object(ApmEventSnapshotStore, "_delete_payload_object")

    assert duplicate.id == existing.id
    assert ApmEventSnapshot.objects.filter(source_event_id=event.event_id).count() == 1
    assert ApmEventSnapshotPayload.objects.filter(snapshot=existing).exists()
    assert ApmEventSnapshotStore.expire_due(now=at, limit=10) == 1
    existing.refresh_from_db()
    assert existing.payload_status == ApmEventSnapshot.PayloadStatus.EXPIRED
    assert existing.pending_payload == {}
    assert not ApmEventSnapshotPayload.objects.filter(snapshot=existing).exists()
    delete_payload.assert_called_once_with("apm/snapshot.json.gz")


def test_retention_delete_failure_keeps_object_index_for_bounded_retry(mocker):
    _, alert, at = _trigger()
    snapshot = alert.snapshots.get()
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        return_value="apm/snapshot.json.gz",
    )
    ApmEventSnapshotStore.persist(snapshot.id)
    snapshot.retention_expires_at = at - timedelta(seconds=1)
    snapshot.save(update_fields=("retention_expires_at", "updated_at"))
    mocker.patch.object(
        ApmEventSnapshotStore,
        "_delete_payload_object",
        side_effect=RuntimeError("minio unavailable"),
    )

    assert ApmEventSnapshotStore.expire_due(now=at, limit=10) == 0
    snapshot.refresh_from_db()
    assert snapshot.payload_status == ApmEventSnapshot.PayloadStatus.UNAVAILABLE
    assert snapshot.payload_error_code == "retention_delete_failed"
    assert ApmEventSnapshotPayload.objects.filter(snapshot=snapshot).exists()
