from unittest.mock import patch

import pytest

from apps.cmdb.models.change_record import COLLECT_AUTOMATION_CHANGE, CREATE_INST, ChangeRecord
from apps.cmdb.models.operation import ChangeRecordMirrorOutbox
from apps.cmdb.services.change_record_mirror import ChangeRecordMirrorService
from apps.cmdb.utils.change_record import batch_create_change_record


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
@patch("apps.cmdb.utils.change_record.SystemMgmt")
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
    [outbox] = ChangeRecordMirrorService.enqueue_payloads(_payloads(100))

    assert ChangeRecordMirrorService.consume(outbox.event_id, owner_token="worker-1") is True
    outbox.refresh_from_db()
    assert outbox.status == "success"
    assert mock_sm.return_value.save_operation_log.call_count == 100


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
