from datetime import timedelta

import pytest
from django.utils.timezone import now

from apps.cmdb.models.change_record import ChangeRecord
from apps.cmdb.models.operation import (
    CmdbOperation,
    CmdbOperationOutbox,
    CmdbOperationOutboxStatus,
    CmdbOperationStatus,
)
from apps.cmdb.services.operation_service import OperationService


pytestmark = pytest.mark.django_db


def _event(event_type="change_record", payload=None):
    operation = CmdbOperation.objects.create(
        operator="alice",
        idempotency_key=f"request-{event_type}",
        request_hash="a" * 64,
        action="instance.create",
        target={"model_id": "host", "instance_id": 9},
        request_snapshot={"inst_name": "host-1"},
        result_snapshot={"_id": 9, "model_id": "host", "inst_name": "host-1"},
        status=CmdbOperationStatus.GRAPH_COMMITTED,
    )
    return CmdbOperationOutbox.objects.create(
        operation=operation,
        event_type=event_type,
        payload=payload or {},
    )


def test_outbox_lease_owner_prevents_stale_completion():
    event = _event()
    assert OperationService.claim_outbox(event.event_id, owner_token="owner-1", lease_seconds=300) is True
    CmdbOperationOutbox.objects.filter(id=event.id).update(lease_expires_at=now() - timedelta(seconds=1))
    assert OperationService.claim_outbox(event.event_id, owner_token="owner-2", lease_seconds=300) is True

    assert OperationService.finish_outbox_success(event.event_id, owner_token="owner-1") is False
    event.refresh_from_db()
    assert event.status == CmdbOperationOutboxStatus.SENDING
    assert event.owner_token == "owner-2"


def test_change_record_consumption_is_idempotent_after_status_reset():
    event = _event()

    assert OperationService.consume_outbox(event.event_id, owner_token="owner-1") is True
    CmdbOperationOutbox.objects.filter(id=event.id).update(
        status=CmdbOperationOutboxStatus.PENDING,
        owner_token="",
        lease_expires_at=None,
    )
    assert OperationService.consume_outbox(event.event_id, owner_token="owner-2") is True

    assert ChangeRecord.objects.filter(operation_event_id=event.event_id).count() == 1
    event.operation.refresh_from_db()
    assert event.operation.status == CmdbOperationStatus.COMPLETED


def test_outbox_failure_is_retryable_without_rolling_back_graph_result(monkeypatch):
    event = _event(event_type="auto_relation")
    monkeypatch.setattr(
        OperationService,
        "_dispatch_outbox",
        classmethod(lambda cls, claimed: (_ for _ in ()).throw(RuntimeError("broker secret-value"))),
    )

    assert OperationService.consume_outbox(event.event_id, owner_token="owner-1") is False

    event.refresh_from_db()
    event.operation.refresh_from_db()
    assert event.status == CmdbOperationOutboxStatus.RETRY
    assert event.attempt_count == 1
    assert "RuntimeError" in event.last_error
    assert "secret-value" not in event.last_error
    assert event.next_attempt_at > now()
    assert event.operation.status == CmdbOperationStatus.GRAPH_COMMITTED


def test_periodic_task_recovers_graph_facts_and_consumes_outbox(monkeypatch):
    from apps.cmdb.tasks.celery_tasks import reconcile_cmdb_operations_task

    monkeypatch.setattr(
        OperationService,
        "recover_stale_graph_writes",
        classmethod(lambda cls: {"scanned": 2, "recovered": 1, "unresolved": 1}),
    )
    monkeypatch.setattr(
        OperationService,
        "process_outbox_batch",
        classmethod(lambda cls: {"scanned": 3, "succeeded": 2, "failed": 1}),
    )

    assert reconcile_cmdb_operations_task() == {
        "graph_writes": {"scanned": 2, "recovered": 1, "unresolved": 1},
        "outbox": {"scanned": 3, "succeeded": 2, "failed": 1},
    }


def test_recover_stale_graph_write_uses_fact_and_creates_outbox(monkeypatch):
    operation = CmdbOperation.objects.create(
        operator="alice",
        idempotency_key="stale-create",
        request_hash="b" * 64,
        action="instance.create",
        target={"model_id": "host"},
        request_snapshot={"inst_name": "host-1"},
        status=CmdbOperationStatus.GRAPH_WRITING,
        owner_token="dead-owner",
        lease_expires_at=now() - timedelta(seconds=1),
    )
    monkeypatch.setattr(
        OperationService,
        "_find_graph_fact",
        staticmethod(lambda op: {"_id": 9, "model_id": "host", "inst_name": "host-1"}),
    )

    stats = OperationService.recover_stale_graph_writes()

    operation.refresh_from_db()
    assert stats == {"scanned": 1, "recovered": 1, "unresolved": 0}
    assert operation.status == CmdbOperationStatus.GRAPH_COMMITTED
    assert operation.outbox_events.count() == 2


def test_process_outbox_batch_aggregates_independent_results(monkeypatch):
    success = _event(event_type="change_record")
    failed = _event(event_type="auto_relation")
    outcomes = {success.event_id: True, failed.event_id: False}
    monkeypatch.setattr(
        OperationService,
        "consume_outbox",
        classmethod(lambda cls, event_id: outcomes[event_id]),
    )

    stats = OperationService.process_outbox_batch()

    assert stats == {"scanned": 2, "succeeded": 1, "failed": 1}
