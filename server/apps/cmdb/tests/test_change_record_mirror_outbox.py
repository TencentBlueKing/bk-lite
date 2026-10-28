from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils.timezone import now

from apps.cmdb.models.change_record import (
    COLLECT_AUTOMATION_CHANGE,
    CREATE_INST,
    MODEL_MANAGEMENT_CHANGE,
    UPDATE_INST,
    ChangeRecord,
)
from apps.cmdb.models.operation import ChangeRecordMirrorOutbox
from apps.cmdb.services.change_record_mirror import ChangeRecordMirrorService
from apps.cmdb.utils.change_record import batch_create_change_record, create_change_record


def _records(count):
    return [
        {
            "inst_id": index,
            "model_id": "host",
            "after_data": {"_id": index, "model_id": "host", "inst_name": f"host-{index}"},
            "model_object": "模型实例",
            "message": f"自动采集新增实例 host-{index}",
        }
        for index in range(count)
    ]


def _payloads(count):
    return [
        {
            "username": "system",
            "source_ip": "127.0.0.1",
            "app": "cmdb",
            "action_type": "create",
            "summary": f"create host-{index}",
            "target_type": "host",
            "target_id": str(index),
            "detail": {"source": "change_record"},
        }
        for index in range(count)
    ]


@pytest.mark.django_db(transaction=True)
@patch("apps.cmdb.services.change_record_mirror.SystemMgmt")
@patch("apps.cmdb.services.change_record_mirror.dispatch_change_record_mirror")
def test_batch_change_records_persist_bounded_outbox_without_sync_rpc(mock_dispatch, mock_sm):
    batch_create_change_record(
        "instance",
        CREATE_INST,
        _records(250),
        operator="system",
        scenario=COLLECT_AUTOMATION_CHANGE,
    )

    assert ChangeRecord.objects.count() == 250
    assert ChangeRecordMirrorOutbox.objects.count() == 3
    assert not mock_sm.return_value.save_operation_log.called
    assert mock_dispatch.call_count == 3


@pytest.mark.django_db(transaction=True)
@patch("apps.cmdb.services.change_record_mirror.SystemMgmt")
def test_outbox_worker_has_fixed_rpc_budget_and_marks_success(mock_sm):
    mock_sm.return_value.save_operation_log.return_value = {"result": True}
    [outbox] = ChangeRecordMirrorService.enqueue_payloads(_payloads(100))

    assert ChangeRecordMirrorService.consume(outbox.event_id, owner_token="worker-1") is True
    outbox.refresh_from_db()
    assert outbox.status == "success"
    assert mock_sm.return_value.save_operation_log.call_count == 100


@pytest.mark.django_db(transaction=True)
@patch("apps.cmdb.services.change_record_mirror.dispatch_change_record_mirror")
@patch("apps.cmdb.services.change_record_mirror.SystemMgmt")
def test_negative_ack_stays_retryable_without_downstream_message(mock_sm, mock_dispatch):
    mock_sm.return_value.save_operation_log.return_value = {"result": False, "message": "unavailable"}
    payloads = _payloads(1)
    [outbox] = ChangeRecordMirrorService.enqueue_payloads(payloads)

    assert ChangeRecordMirrorService.consume(outbox.event_id, owner_token="worker-1") is False
    outbox.refresh_from_db()
    assert outbox.status == "retry"
    assert outbox.payloads == payloads
    assert "unavailable" not in outbox.last_error
    assert outbox.last_error == "operation_log_rejected"
    assert outbox.next_attempt_at > now()

    ChangeRecordMirrorOutbox.objects.filter(pk=outbox.pk).update(next_attempt_at=now() - timedelta(seconds=1))
    assert ChangeRecordMirrorService.recover_ready() == 1
    mock_dispatch.assert_called_once_with(outbox.event_id)


@pytest.mark.django_db
@patch("apps.cmdb.services.change_record_mirror.dispatch_change_record_mirror")
@patch("apps.cmdb.services.change_record_mirror.SystemMgmt")
def test_single_model_edit_false_receipt_stays_retryable(mock_sm, mock_dispatch):
    mock_sm.return_value.save_operation_log.return_value = {"result": False, "message": "unavailable"}
    create_change_record(
        inst_id=42,
        model_id="host",
        label="模型管理",
        _type=UPDATE_INST,
        operator="alice",
        message="修改模型. 模型名称: 旧名称",
        model_object="模型管理",
        scenario=MODEL_MANAGEMENT_CHANGE,
        before_data={"model_name": "旧名称"},
        after_data={"model_name": "新名称"},
    )

    assert ChangeRecord.objects.filter(inst_id=42).exists()
    assert not mock_sm.return_value.save_operation_log.called
    [outbox] = list(ChangeRecordMirrorOutbox.objects.all())
    assert ChangeRecordMirrorService.consume(outbox.event_id, owner_token="worker-1") is False
    outbox.refresh_from_db()
    assert outbox.status == "retry"
    assert outbox.last_error == "operation_log_rejected"
    assert "unavailable" not in outbox.last_error
    assert ChangeRecord.objects.filter(inst_id=42).exists()

    ChangeRecordMirrorOutbox.objects.filter(pk=outbox.pk).update(next_attempt_at=now() - timedelta(seconds=1))
    assert ChangeRecordMirrorService.recover_ready() == 1
    mock_dispatch.assert_called_once_with(outbox.event_id)


@pytest.mark.django_db(transaction=True)
@patch("apps.cmdb.services.change_record_mirror.dispatch_change_record_mirror")
@patch("apps.cmdb.services.change_record_mirror.SystemMgmt")
def test_negative_ack_stops_after_max_attempts(mock_sm, mock_dispatch):
    mock_sm.return_value.save_operation_log.return_value = {"result": False, "message": "unavailable"}
    [outbox] = ChangeRecordMirrorService.enqueue_payloads(_payloads(1))
    ChangeRecordMirrorOutbox.objects.filter(pk=outbox.pk).update(attempt_count=ChangeRecordMirrorService.MAX_ATTEMPTS - 1)

    assert ChangeRecordMirrorService.consume(outbox.event_id, owner_token="worker-1") is False
    outbox.refresh_from_db()
    assert outbox.status == "failed"
    assert outbox.attempt_count == ChangeRecordMirrorService.MAX_ATTEMPTS
    assert "unavailable" not in outbox.last_error
    assert ChangeRecordMirrorService.recover_ready() == 0
    mock_dispatch.assert_not_called()


@pytest.mark.django_db(transaction=True)
@patch("apps.cmdb.services.change_record_mirror.SystemMgmt")
def test_partial_ack_replays_only_unacked_payload(mock_sm):
    payloads = _payloads(2)
    mock_sm.return_value.save_operation_log.side_effect = [
        {"result": True},
        {"result": False, "message": "unavailable"},
        {"result": True},
    ]
    [outbox] = ChangeRecordMirrorService.enqueue_payloads(payloads)

    assert ChangeRecordMirrorService.consume(outbox.event_id, owner_token="worker-1") is False
    outbox.refresh_from_db()
    assert outbox.payloads == [payloads[1]]
    assert "unavailable" not in outbox.last_error

    ChangeRecordMirrorOutbox.objects.filter(pk=outbox.pk).update(next_attempt_at=now() - timedelta(seconds=1))
    assert ChangeRecordMirrorService.consume(outbox.event_id, owner_token="worker-2") is True
    sent_ids = [call.kwargs["target_id"] for call in mock_sm.return_value.save_operation_log.call_args_list]
    assert sent_ids == [payloads[0]["target_id"], payloads[1]["target_id"], payloads[1]["target_id"]]
    outbox.refresh_from_db()
    assert outbox.status == "success"


@pytest.mark.django_db(transaction=True)
@patch(
    "apps.cmdb.tasks.celery_tasks.consume_change_record_mirror_outbox.delay",
    side_effect=RuntimeError("broker secret should not escape"),
)
def test_broker_failure_keeps_outbox_pending_without_breaking_batch_write(_mock_delay):
    batch_create_change_record(
        "instance",
        CREATE_INST,
        _records(1),
        operator="system",
        scenario=COLLECT_AUTOMATION_CHANGE,
    )

    assert ChangeRecord.objects.count() == 1
    assert ChangeRecordMirrorOutbox.objects.filter(status="pending").count() == 1


def test_mirror_outbox_recovery_is_registered_in_beat():
    from apps.cmdb.config import CELERY_BEAT_SCHEDULE

    schedule = CELERY_BEAT_SCHEDULE["recover_change_record_mirror_outbox_task"]
    assert schedule["task"] == "apps.cmdb.tasks.celery_tasks.recover_change_record_mirror_outbox_task"
