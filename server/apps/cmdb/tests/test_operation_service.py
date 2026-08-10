import pytest

from apps.cmdb.models.operation import CmdbOperation, CmdbOperationOutbox, CmdbOperationStatus
from apps.cmdb.services.operation_service import OperationConflict, OperationService


pytestmark = pytest.mark.django_db


def test_same_operator_and_idempotency_key_reuses_only_same_request():
    first = OperationService.start(
        operator="alice",
        idempotency_key="request-1",
        action="instance.create",
        target={"model_id": "host"},
        request_payload={"inst_name": "host-1"},
    )
    second = OperationService.start(
        operator="alice",
        idempotency_key="request-1",
        action="instance.create",
        target={"model_id": "host"},
        request_payload={"inst_name": "host-1"},
    )

    assert second.operation.id == first.operation.id
    assert first.reused is False
    assert second.reused is True

    with pytest.raises(OperationConflict):
        OperationService.start(
            operator="alice",
            idempotency_key="request-1",
            action="instance.create",
            target={"model_id": "host"},
            request_payload={"inst_name": "host-2"},
        )


def test_graph_write_is_executed_once_and_creates_unique_outbox_events():
    started = OperationService.start(
        operator="alice",
        idempotency_key="request-1",
        action="instance.create",
        target={"model_id": "host"},
        request_payload={"inst_name": "host-1"},
    )
    calls = []

    def graph_write(operation_id):
        calls.append(operation_id)
        return {"_id": 9, "model_id": "host", "inst_name": "host-1"}

    events = [
        ("change_record", {"operator": "alice"}),
        ("auto_relation", {"instance_ids": [9]}),
    ]
    first = OperationService.execute_graph(started.operation, graph_write=graph_write, events=events)
    second = OperationService.execute_graph(started.operation, graph_write=graph_write, events=events)

    started.operation.refresh_from_db()
    assert first == second
    assert len(calls) == 1
    assert started.operation.status == CmdbOperationStatus.GRAPH_COMMITTED
    assert started.operation.result_snapshot == first
    assert CmdbOperationOutbox.objects.filter(operation=started.operation).count() == 2


def test_only_one_owner_can_claim_pending_graph_write():
    started = OperationService.start(
        operator="alice",
        idempotency_key="request-1",
        action="instance.create",
        target={"model_id": "host"},
        request_payload={"inst_name": "host-1"},
    )

    first = OperationService.claim_graph_write(started.operation.operation_id, owner_token="worker-1")
    second = OperationService.claim_graph_write(started.operation.operation_id, owner_token="worker-2")

    started.operation.refresh_from_db()
    assert first is True
    assert second is False
    assert started.operation.status == CmdbOperationStatus.GRAPH_WRITING
    assert started.operation.owner_token == "worker-1"


def test_graph_error_marks_operation_error_without_outbox():
    started = OperationService.start(
        operator="alice",
        idempotency_key="request-1",
        action="instance.update",
        target={"instance_id": 9},
        request_payload={"inst_name": "host-2"},
    )

    with pytest.raises(RuntimeError, match="graph unavailable"):
        OperationService.execute_graph(
            started.operation,
            graph_write=lambda operation_id: (_ for _ in ()).throw(RuntimeError("graph unavailable secret")),
            events=[],
        )

    started.operation.refresh_from_db()
    assert started.operation.status == CmdbOperationStatus.ERROR
    assert "RuntimeError" in started.operation.last_error
    assert "secret" not in started.operation.last_error
    assert not CmdbOperationOutbox.objects.filter(operation=started.operation).exists()


def test_pending_recovery_checks_graph_fact_before_committing():
    started = OperationService.start(
        operator="alice",
        idempotency_key="request-1",
        action="instance.create",
        target={"model_id": "host"},
        request_payload={"inst_name": "host-1"},
    )
    events = [("auto_relation", {"instance_ids": [9]})]

    recovered = OperationService.recover_pending(
        started.operation,
        fact_finder=lambda operation_id: {"_id": 9, "model_id": "host", "inst_name": "host-1"},
        events=events,
    )

    started.operation.refresh_from_db()
    assert recovered == {"_id": 9, "model_id": "host", "inst_name": "host-1"}
    assert started.operation.status == CmdbOperationStatus.GRAPH_COMMITTED
    assert CmdbOperationOutbox.objects.filter(operation=started.operation, event_type="auto_relation").exists()
