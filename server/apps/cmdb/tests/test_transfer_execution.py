import logging
from unittest.mock import Mock

import pytest

from apps.cmdb.services.transfer_execution import TransferExecution
from apps.cmdb.services.transfer_service import TransferService
from apps.cmdb.tests.test_transfer_service import submit


def _lifecycle(records, event):
    return [record for record in records if record.msg.startswith(event)]


def test_export_logs_start_and_finish_without_request_payload(transfer_owner, monkeypatch, caplog):
    task = submit(
        transfer_owner,
        model_id="host\nline",
        params={"scope": "all", "attr_list": ["inst_name"], "association_list": [], "inst_uuids": [], "note": "EXPORT-PAYLOAD-SENTINEL"},
    )
    monkeypatch.setattr("apps.cmdb.services.transfer_execution.TransferAuthorization.revalidate", Mock(return_value=object()))
    monkeypatch.setattr(TransferExecution, "export", Mock(return_value=({"exported": 2}, {"result": {"key": "transfer/result"}})))
    with caplog.at_level(logging.INFO, logger="cmdb"):
        TransferExecution.run(task.pk, files=Mock())
    result = TransferService.get(transfer_owner, task.pk)
    assert result.status == "succeeded" and not result.holds_slot
    assert result.summary == {"exported": 2}
    assert result.error_code == ""
    started = _lifecycle(caplog.records, "event=cmdb_transfer_started")
    finished = _lifecycle(caplog.records, "event=cmdb_transfer_finished")
    assert len(started) == 1 and len(finished) == 1
    assert started[0].msg == "event=cmdb_transfer_started task_id=%s kind=%s model_id=%s"
    assert started[0].args == (str(task.pk), "export", "host\\nline")
    assert finished[0].msg == "event=cmdb_transfer_finished task_id=%s kind=%s status=%s holds_slot=%s error_code=%s"
    assert finished[0].args == (str(task.pk), "export", "succeeded", "false", "-")
    assert started[0].exc_info is None and finished[0].exc_info is None
    rendered = logging.Formatter().format(started[0]) + logging.Formatter().format(finished[0])
    assert "event=cmdb_transfer_started" in started[0].getMessage()
    assert f"task_id={task.pk}" in finished[0].getMessage()
    assert "status=succeeded" in finished[0].getMessage()
    assert "holds_slot=false" in finished[0].getMessage()
    assert "\n" not in started[0].getMessage()
    assert "EXPORT-PAYLOAD-SENTINEL" not in rendered
    assert not _lifecycle(caplog.records, "event=cmdb_transfer_failed")


def test_slot_rejected_claim_does_not_log_execution_lifecycle(transfer_owner, caplog):
    task = submit(transfer_owner)
    token = TransferService.claim(task.pk)
    files = Mock()
    with caplog.at_level(logging.INFO, logger="cmdb"):
        TransferExecution.run(task.pk, files=files)
    result = TransferService.get(transfer_owner, task.pk)
    assert result.status == "running" and result.holds_slot and result.execution_token == token
    files.put.assert_not_called()
    assert _lifecycle(caplog.records, "event=cmdb_transfer_started") == []
    assert _lifecycle(caplog.records, "event=cmdb_transfer_finished") == []


def test_disabled_owner_export_fails_without_reading_files(transfer_owner):
    task = submit(transfer_owner)
    transfer_owner.disabled = True
    transfer_owner.save(update_fields=["disabled"])
    files = Mock()
    TransferExecution.run(task.pk, files=files)
    result = TransferService.get(transfer_owner, task.pk)
    assert result.status == "failed" and result.error_code == "owner_disabled"
    assert not result.holds_slot
    files.put.assert_not_called()


def test_unexpected_failure_is_sanitized_and_import_not_replayed(transfer_owner, monkeypatch, caplog):
    task = submit(transfer_owner, kind="import")
    error = RuntimeError("PRIVATE-PAYLOAD-SENTINEL")
    monkeypatch.setattr("apps.cmdb.services.transfer_execution.TransferAuthorization.revalidate", Mock(side_effect=error))
    with caplog.at_level(logging.INFO, logger="cmdb"):
        TransferExecution.run(task.pk, files=Mock())
    task = TransferService.get(transfer_owner, task.pk)
    assert task.status == "failed" and not task.holds_slot
    assert task.message.startswith("RuntimeError: PRIVATE-PAYLOAD-SENTINEL")
    assert "transfer_execution.py" in task.message
    assert not task.summary["_failure"]["result_uncertain"]
    records = [record for record in caplog.records if "cmdb_transfer_failed" in record.msg]
    assert len(records) == 1
    assert records[0].args[0] == str(task.pk)
    assert records[0].exc_info[2] is error.__traceback__
    assert "PRIVATE-PAYLOAD-SENTINEL" not in logging.Formatter().format(records[0])
    finished = _lifecycle(caplog.records, "event=cmdb_transfer_finished")
    started = _lifecycle(caplog.records, "event=cmdb_transfer_started")
    assert len(started) == 1 and len(finished) == 1
    assert finished[0].msg == "event=cmdb_transfer_finished task_id=%s kind=%s status=%s holds_slot=%s error_code=%s"
    assert finished[0].args == (str(task.pk), "import", "failed", "false", "execution_failed")
    assert finished[0].exc_info is None
    assert "error_code=execution_failed" in finished[0].getMessage()
    assert "PRIVATE-PAYLOAD-SENTINEL" not in logging.Formatter().format(finished[0])
    assert str(error) == "PRIVATE-PAYLOAD-SENTINEL"
    assert not TransferService.claim(task.pk)


@pytest.mark.parametrize("code,hint", [("AccessDenied", "权限"), ("NoSuchBucket", "存储桶"), ("PRIVATE-CODE-SENTINEL", "操作失败")])
def test_storage_error_keeps_diagnostic_code_without_leaking_response(transfer_owner, monkeypatch, caplog, code, hint):
    from minio.error import S3Error

    task = submit(transfer_owner)
    error = S3Error(code, "PRIVATE-RESPONSE-SENTINEL", "PRIVATE-RESOURCE-SENTINEL", "request", "host", None)
    monkeypatch.setattr("apps.cmdb.services.transfer_execution.TransferAuthorization.revalidate", Mock(return_value=object()))
    monkeypatch.setattr(TransferExecution, "export", Mock(side_effect=error))
    with caplog.at_level(logging.ERROR, logger="cmdb"):
        TransferExecution.run(task.pk, files=Mock())
    result = TransferService.get(transfer_owner, task.pk)
    assert result.status == "failed" and not result.holds_slot
    assert result.error_code == "storage_unavailable"
    assert hint in result.message
    records = [record for record in caplog.records if "cmdb_transfer_failed" in record.msg]
    assert len(records) == 1
    public_code = "OtherS3Error" if code == "PRIVATE-CODE-SENTINEL" else code
    assert records[0].msg == "event=cmdb_transfer_failed task_id=%s failed_stage=%s error_type=%s storage_code=%s"
    assert records[0].args == (str(task.pk), "object_storage", "S3Error", public_code)
    assert f"storage_code={public_code}" in records[0].getMessage()
    assert "failed_stage=object_storage" in records[0].getMessage()
    assert records[0].exc_info[2] is error.__traceback__
    formatted = logging.Formatter().format(records[0])
    assert "PRIVATE-RESPONSE-SENTINEL" not in formatted
    assert "PRIVATE-RESOURCE-SENTINEL" not in formatted
    assert "PRIVATE-CODE-SENTINEL" not in formatted
    assert error.code == code and error.message == "PRIVATE-RESPONSE-SENTINEL"


def test_export_download_ignores_deleted_instances_and_authorization_drift(monkeypatch):
    from types import SimpleNamespace

    from apps.cmdb.services.transfer_service import TransferError

    revalidate = Mock(side_effect=TransferError("authorization_changed", "权限范围已变化，请按当前权限重新提交", 403))
    monkeypatch.setattr("apps.cmdb.services.transfer_execution.TransferAuthorization.revalidate", revalidate)
    query = Mock(side_effect=AssertionError("download must not reload instances"))
    monkeypatch.setattr("apps.cmdb.services.transfer_execution.InstanceManage.query_entity_by_uuids", query)
    files = Mock()
    files.local_copy.side_effect = AssertionError("download must not reread the export manifest")
    TransferExecution.validate_download(SimpleNamespace(kind="export"), files)
    revalidate.assert_not_called()
    query.assert_not_called()
    files.local_copy.assert_not_called()


def test_import_error_report_download_still_revalidates(monkeypatch):
    from types import SimpleNamespace

    revalidate = Mock(return_value=object())
    monkeypatch.setattr("apps.cmdb.services.transfer_execution.TransferAuthorization.revalidate", revalidate)
    task = SimpleNamespace(kind="import")
    TransferExecution.validate_download(task, Mock())
    revalidate.assert_called_once_with(task)
