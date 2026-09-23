import logging
from unittest.mock import Mock

import pytest

from apps.cmdb.services.transfer_execution import TransferExecution
from apps.cmdb.services.transfer_service import TransferService
from apps.cmdb.tests.test_transfer_service import submit


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
    with caplog.at_level(logging.ERROR, logger="cmdb"):
        TransferExecution.run(task.pk, files=Mock())
    task = TransferService.get(transfer_owner, task.pk)
    assert task.status == "interrupted" and task.holds_slot
    records = [record for record in caplog.records if "cmdb_transfer_failed" in record.msg]
    assert len(records) == 1
    assert records[0].args[0] == str(task.pk)
    assert records[0].exc_info[2] is error.__traceback__
    assert "PRIVATE-PAYLOAD-SENTINEL" not in logging.Formatter().format(records[0])
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
