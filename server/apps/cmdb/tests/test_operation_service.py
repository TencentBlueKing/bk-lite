import logging

import pytest

from apps.cmdb.models.operation import CmdbOperationOutbox, CmdbOperationStatus
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


def test_reused_operation_keeps_original_event_context():
    first = OperationService.start(
        operator="alice",
        idempotency_key="context-request-1",
        action="instance.update",
        target={"model_id": "host", "inst_uuid": "00000000-0000-0000-0000-000000000009"},
        request_payload={"update_attr": {"interfaces": []}},
        event_context={"before_data": {"interfaces": [{"name": "eth0"}]}},
    )
    second = OperationService.start(
        operator="alice",
        idempotency_key="context-request-1",
        action="instance.update",
        target={"model_id": "host", "inst_uuid": "00000000-0000-0000-0000-000000000009"},
        request_payload={"update_attr": {"interfaces": []}},
        event_context={"before_data": {"interfaces": [{"name": "should-not-overwrite"}]}},
    )

    second.operation.refresh_from_db()
    assert second.operation.id == first.operation.id
    assert second.reused is True
    assert second.operation.event_context == {"before_data": {"interfaces": [{"name": "eth0"}]}}


def test_events_for_operation_restores_audit_context():
    started = OperationService.start(
        operator="alice",
        idempotency_key="context-recovery-1",
        action="instance.update",
        target={"model_id": "host", "inst_uuid": "00000000-0000-0000-0000-000000000009"},
        request_payload={"update_attr": {"interfaces": []}},
        event_context={
            "scenario": "ordinary_attribute_change",
            "before_data": {"interfaces": [{"name": "eth0"}]},
            "attribute_snapshot": {"version": 1, "attributes": {"interfaces": {"attr_type": "table"}}},
        },
    )

    assert OperationService.events_for_operation(started.operation) == [
        ("change_record", started.operation.event_context),
        ("auto_relation", {}),
    ]


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


@pytest.mark.django_db(transaction=True)
def test_graph_commit_immediately_dispatches_persisted_outbox_events(monkeypatch):
    dispatched = []
    monkeypatch.setattr(
        "apps.cmdb.tasks.celery_tasks.consume_cmdb_operation_outbox.delay",
        lambda event_id: dispatched.append(event_id),
    )
    started = OperationService.start(
        operator="alice",
        idempotency_key="dispatch-request-1",
        action="instance.create",
        target={"model_id": "host"},
        request_payload={"inst_name": "host-1"},
    )

    OperationService.execute_graph(
        started.operation,
        graph_write=lambda operation_id: {"_id": 9, "model_id": "host", "inst_name": "host-1"},
        events=[("change_record", {}), ("auto_relation", {})],
    )

    persisted_event_ids = {
        str(event_id) for event_id in CmdbOperationOutbox.objects.filter(operation=started.operation).values_list("event_id", flat=True)
    }
    assert set(dispatched) == persisted_event_ids


@pytest.mark.django_db(transaction=True)
def test_broker_dispatch_failure_keeps_committed_outbox_pending(monkeypatch, caplog):
    sensitive_sentinel = "SECRET_BROKER_RESPONSE_BODY"
    original_error = RuntimeError(sensitive_sentinel)

    def fail_dispatch(_event_id):
        raise original_error

    monkeypatch.setattr(
        "apps.cmdb.tasks.celery_tasks.consume_cmdb_operation_outbox.delay",
        fail_dispatch,
    )
    started = OperationService.start(
        operator="alice",
        idempotency_key="dispatch-request-broker-down",
        action="instance.update",
        target={"model_id": "host", "inst_uuid": "00000000-0000-0000-0000-000000000009"},
        request_payload={"inst_name": "host-2"},
    )

    with caplog.at_level(logging.ERROR, logger="cmdb"):
        result = OperationService.execute_graph(
            started.operation,
            graph_write=lambda operation_id: {"_id": 9, "model_id": "host", "inst_name": "host-2"},
            events=[("change_record", {})],
        )

    assert result["inst_name"] == "host-2"
    assert set(CmdbOperationOutbox.objects.filter(operation=started.operation).values_list("status", flat=True)) == {"pending"}
    records = [record for record in caplog.records if record.msg.startswith("event=cmdb_operation_outbox_dispatch_failed")]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=cmdb_operation_outbox_dispatch_failed event_id=%s failed_stage=%s error_type=%s"
    assert record.args[1:] == ("broker_dispatch", "RuntimeError")
    assert record.getMessage().endswith("failed_stage=broker_dispatch error_type=RuntimeError")
    assert record.exc_info is not None
    assert record.exc_info[2] is original_error.__traceback__
    assert record.exc_info[1] is not original_error
    assert original_error.args == (sensitive_sentinel,)
    assert sensitive_sentinel not in caplog.text


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
