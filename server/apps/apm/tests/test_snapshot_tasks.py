from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.config import CELERY_BEAT_SCHEDULE
from apps.apm.models import ApmEventSnapshot, ApmEventSnapshotPayload, ApmPolicy, ApmService, ApmServiceOrganization
from apps.apm.services import DjangoApmPolicyService
from apps.apm.tests.helpers import bind_policy_organizations
from apps.apm.services.contracts import ServiceRed, ServiceRedPoint
from apps.apm.tasks import expire_apm_event_snapshot_payloads, persist_apm_event_snapshot_payloads

pytestmark = pytest.mark.django_db


def _assert_outside_atomic():
    extra = [block for block in connection.atomic_blocks if not getattr(block, "_from_testcase", False)]
    assert extra == []
    assert connection.savepoint_ids == []


@pytest.fixture(autouse=True)
def snapshot_object_storage(mocker):
    def upload_outside_atomic(*args, **kwargs):
        _assert_outside_atomic()
        return "apm/test-snapshot.json.gz"

    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        side_effect=upload_outside_atomic,
    )


class MetricStore:
    def __init__(self, at):
        self.red = ServiceRed(10, 0.2, 100, 150, (ServiceRedPoint(at, 10, 0.2, 100, 150),))

    def service_red(self, query):
        return self.red


def _trigger():
    at = timezone.now().replace(second=0, microsecond=0)
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name="checkout",
        normalized_name="checkout",
        first_seen_at=at,
        last_seen_at=at,
    )
    ApmServiceOrganization.objects.create(service=service, organization=10)
    policy = ApmPolicy.objects.create(
        name="错误率",
        service=service,
        environment="production",
        endpoints=["POST /checkout"],
        metric_type="error_rate",
        thresholds=[{"severity": "error", "comparator": "gt", "value": "0.1"}],
        trigger_after=1,
        recover_after=1,
    )
    bind_policy_organizations(policy)
    DjangoApmPolicyService(MetricStore(at), InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=at)
    return ApmEventSnapshot.objects.get(), at


def test_snapshot_payload_tasks_are_beat_driven_and_not_in_batch_init():
    assert CELERY_BEAT_SCHEDULE["apm_persist_event_snapshot_payloads"]["task"] == ("apps.apm.tasks.persist_apm_event_snapshot_payloads")
    assert CELERY_BEAT_SCHEDULE["apm_expire_event_snapshot_payloads"]["task"] == ("apps.apm.tasks.expire_apm_event_snapshot_payloads")
    with open("apps/core/management/commands/batch_init.py", encoding="utf-8") as file:
        batch_init = file.read()
    assert "persist_apm_event_snapshot_payloads" not in batch_init
    assert "expire_apm_event_snapshot_payloads" not in batch_init


def test_persist_task_writes_pending_snapshot_payloads():
    snapshot, _ = _trigger()
    assert snapshot.payload_status == ApmEventSnapshot.PayloadStatus.PENDING
    assert snapshot.pending_payload

    result = persist_apm_event_snapshot_payloads.run()
    snapshot.refresh_from_db()

    assert result == {"processed": 1, "available": 1, "unavailable": 0}
    assert snapshot.payload_status == ApmEventSnapshot.PayloadStatus.AVAILABLE
    assert snapshot.pending_payload == {}
    assert ApmEventSnapshotPayload.objects.filter(snapshot=snapshot).exists()


def test_persist_task_skips_empty_payload_and_exhausted_retries():
    snapshot, _ = _trigger()
    snapshot.pending_payload = {}
    snapshot.save(update_fields=("pending_payload", "updated_at"))
    empty = persist_apm_event_snapshot_payloads.run()

    snapshot.pending_payload = {"series": []}
    snapshot.payload_attempts = 8
    snapshot.save(update_fields=("pending_payload", "payload_attempts", "updated_at"))
    exhausted = persist_apm_event_snapshot_payloads.run()

    assert empty == {"processed": 0, "available": 0, "unavailable": 0}
    assert exhausted == {"processed": 0, "available": 0, "unavailable": 0}


def test_persist_task_marks_unavailable_when_upload_fails(mocker):
    snapshot, _ = _trigger()

    def fail_upload(*args, **kwargs):
        _assert_outside_atomic()
        raise RuntimeError("minio unavailable")

    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        side_effect=fail_upload,
    )

    result = persist_apm_event_snapshot_payloads.run()
    snapshot.refresh_from_db()

    assert result == {"processed": 1, "available": 0, "unavailable": 1}
    assert snapshot.payload_status == ApmEventSnapshot.PayloadStatus.UNAVAILABLE
    assert snapshot.payload_error_code == "object_storage_unavailable"
    assert snapshot.pending_payload
    assert snapshot.payload_attempts == 1
    assert not ApmEventSnapshotPayload.objects.filter(snapshot=snapshot).exists()


def test_expire_task_clears_due_snapshot_payloads(mocker):
    snapshot, at = _trigger()
    persist_apm_event_snapshot_payloads.run()
    snapshot.refresh_from_db()
    snapshot.retention_expires_at = at - timedelta(seconds=1)
    snapshot.save(update_fields=("retention_expires_at", "updated_at"))

    def delete_outside_atomic(payload_path):
        _assert_outside_atomic()

    delete_payload = mocker.patch(
        "apps.apm.services.snapshots.ApmEventSnapshotStore._delete_payload_object",
        side_effect=delete_outside_atomic,
    )

    result = expire_apm_event_snapshot_payloads.run()
    snapshot.refresh_from_db()

    assert result == {"expired": 1}
    assert snapshot.payload_status == ApmEventSnapshot.PayloadStatus.EXPIRED
    assert snapshot.pending_payload == {}
    assert not ApmEventSnapshotPayload.objects.filter(snapshot=snapshot).exists()
    delete_payload.assert_called_once()


def test_expire_task_keeps_payload_when_delete_fails(mocker):
    snapshot, at = _trigger()
    persist_apm_event_snapshot_payloads.run()
    snapshot.refresh_from_db()
    snapshot.retention_expires_at = at - timedelta(seconds=1)
    snapshot.save(update_fields=("retention_expires_at", "updated_at"))

    def fail_delete(payload_path):
        _assert_outside_atomic()
        raise RuntimeError("minio unavailable")

    mocker.patch(
        "apps.apm.services.snapshots.ApmEventSnapshotStore._delete_payload_object",
        side_effect=fail_delete,
    )

    result = expire_apm_event_snapshot_payloads.run()
    snapshot.refresh_from_db()

    assert result == {"expired": 0}
    assert snapshot.payload_status == ApmEventSnapshot.PayloadStatus.UNAVAILABLE
    assert snapshot.payload_error_code == "retention_delete_failed"
    assert ApmEventSnapshotPayload.objects.filter(snapshot=snapshot).exists()
