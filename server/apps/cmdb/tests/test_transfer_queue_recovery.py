import json

import pytest

from apps.cmdb.services.transfer_service import TransferError, TransferService
from apps.cmdb.tests.test_transfer_service import submit
from apps.cmdb.tests.test_transfer_views import request_view


def test_running_import_accepts_more_tasks_until_five_and_history_stays_visible(transfer_owner):
    history = []
    for index in range(5):
        task = submit(transfer_owner, key=f"history-{index}")
        TransferService.cancel(transfer_owner, task.pk)
        history.append(task.pk)
    first = submit(transfer_owner, key="running", kind="import")
    token = TransferService.claim(first.pk)
    queued = [submit(transfer_owner, key=f"queued-{index}", kind="import") for index in range(4)]
    assert TransferService.claim(queued[0].pk) is None
    with pytest.raises(TransferError) as error:
        submit(transfer_owner, key="sixth")
    assert error.value.code == "active_task_limit"
    data = json.loads(request_view(transfer_owner, "list").content)["data"]
    assert len(data["items"]) == 10
    assert not data["can_submit"]
    assert set(history).issubset({task.pk for task in TransferService.list(transfer_owner)})
    assert TransferService.finish(first.pk, token, "succeeded")
    assert TransferService.claim(queued[0].pk)
    assert json.loads(request_view(transfer_owner, "list").content)["data"]["can_submit"]
    assert len(TransferService.list(transfer_owner)) == 9


def test_import_exception_is_failed_releases_slot_and_preserves_confirmed_counts(transfer_owner, monkeypatch, caplog):
    import logging
    from unittest.mock import Mock

    from apps.cmdb.services.transfer_execution import TransferExecution

    task = submit(transfer_owner, kind="import")
    error = RuntimeError("SECRET-IMPORT-PAYLOAD")
    monkeypatch.setattr("apps.cmdb.services.transfer_execution.TransferAuthorization.revalidate", Mock(return_value=object()))

    def broken_import(task, token, *args):
        TransferService.progress(task.pk, token, "writing_instances", 1, 3, {"created": 1, "updated": 0, "failed_rows": 0})
        raise error

    monkeypatch.setattr(TransferExecution, "import_file", broken_import)
    with caplog.at_level(logging.ERROR, logger="cmdb"):
        TransferExecution.run(task.pk, files=Mock())
    result = TransferService.get(transfer_owner, task.pk)
    assert result.status == "failed" and not result.holds_slot
    data = json.loads(request_view(transfer_owner, "retrieve", task_id=task.pk).content)["data"]
    assert data["failure"]["stage"] == "writing_instances"
    assert data["failure"]["result_uncertain"]
    assert data["summary"]["created"] == 1
    assert data["summary"]["updated"] is None
    assert data["message"].startswith("RuntimeError: SECRET-IMPORT-PAYLOAD")
    assert "transfer_queue_recovery.py" in data["message"]
    records = [r for r in caplog.records if "cmdb_transfer_failed" in r.msg]
    assert len(records) == 1 and records[0].exc_info[2] is error.__traceback__
    assert records[0].args[1:3] == ("writing_instances", "RuntimeError")
    assert "SECRET-IMPORT-PAYLOAD" not in logging.Formatter().format(records[0])
    assert str(error) == "SECRET-IMPORT-PAYLOAD"
    next_task = submit(transfer_owner, key="next", kind="import")
    assert TransferService.claim(next_task.pk)
    assert not TransferService.claim(task.pk)


def test_watchdog_failure_does_not_release_live_worker_but_worker_exit_does(transfer_owner, monkeypatch):
    from unittest.mock import Mock

    from apps.cmdb.services.transfer_execution import TransferExecution

    task = submit(transfer_owner, kind="import")
    monkeypatch.setattr("apps.cmdb.services.transfer_execution.TransferAuthorization.revalidate", Mock(return_value=object()))

    def late_worker(task, token, *args):
        TransferService.progress(task.pk, token, "writing_instances", 0, 1, {"created": 0})
        assert TransferService.interrupt(task.pk, token, "worker_lost")
        result = TransferService.get(transfer_owner, task.pk)
        assert result.status == "failed" and result.holds_slot
        queued = submit(transfer_owner, key="next", kind="import")
        assert TransferService.claim(queued.pk) is None
        assert not TransferService.finish(task.pk, token, "succeeded")
        raise TimeoutError("PRIVATE-ENDPOINT")

    monkeypatch.setattr(TransferExecution, "import_file", late_worker)
    TransferExecution.run(task.pk, files=Mock())
    result = TransferService.get(transfer_owner, task.pk)
    assert result.status == "failed" and not result.holds_slot
    assert TransferService.claim(submit(transfer_owner, key="next", kind="import").pk)


def test_legacy_expired_interruption_is_visible_failed_and_does_not_block_submission(transfer_owner):
    from datetime import timedelta
    from unittest.mock import Mock

    from django.utils.timezone import now

    from apps.cmdb.models.transfer_task import CmdbTransferTask
    from apps.cmdb.services.transfer_maintenance import TransferMaintenance

    task = submit(transfer_owner, kind="import", source_key="transfer/tmp/old/source.xlsx")
    token = TransferService.claim(task.pk)
    CmdbTransferTask.objects.filter(pk=task.pk).update(
        status="interrupted",
        phase="interrupted",
        error_code="worker_lost",
        summary={"created": 0, "updated": 0},
        expires_at=now() - timedelta(days=1),
    )
    data = json.loads(request_view(transfer_owner, "list").content)["data"]
    assert data["can_submit"]
    assert data["items"][0]["status"] == "failed"
    assert data["items"][0]["summary"] == {"created": None, "updated": None}
    assert data["items"][0]["failure"]["execution_pending"]
    assert not data["items"][0]["available_actions"]
    assert "核对" not in data["items"][0]["message"]
    queued = submit(transfer_owner, key="next", kind="import")
    assert not TransferService.claim(queued.pk)
    assert not TransferService.fail_execution(task.pk, "stale-token", "error", "error", execution_stopped=True)
    assert request_view(transfer_owner, "destroy", "delete", task.pk).status_code == 409
    files = Mock()
    files.scan.return_value = []
    TransferMaintenance.cleanup(files)
    files.delete.assert_not_called()
    assert TransferService.fail_execution(task.pk, token, "execution_stopped", "执行结束", execution_stopped=True)
    assert TransferService.claim(queued.pk)
    TransferMaintenance.cleanup(files)
    files.delete.assert_called_once_with(task.source_key)
    assert not CmdbTransferTask.objects.filter(pk=task.pk).exists()


def test_import_queue_is_fifo_but_other_models_and_exports_can_run(transfer_owner):
    first = submit(transfer_owner, key="first", kind="import")
    second = submit(transfer_owner, key="second", kind="import")
    other = submit(transfer_owner, key="other", kind="import", model_id="mysql")
    export = submit(transfer_owner, key="export")
    assert not TransferService.claim(second.pk)
    assert TransferService.claim(other.pk)
    export_token = TransferService.claim(export.pk)
    assert export_token
    TransferService.cancel(transfer_owner, first.pk)
    assert not TransferService.claim(second.pk)  # 全局两个执行名额已满。
    TransferService.finish(export.pk, export_token, "succeeded")
    assert TransferService.claim(second.pk)


def test_late_success_cannot_publish_artifacts_and_releases_slot_when_returning(transfer_owner, monkeypatch):
    from unittest.mock import Mock

    from apps.cmdb.services.transfer_execution import TransferExecution

    task = submit(transfer_owner, kind="import")
    monkeypatch.setattr("apps.cmdb.services.transfer_execution.TransferAuthorization.revalidate", Mock(return_value=object()))

    def late_success(task, token, *args):
        TransferService.progress(task.pk, token, "writing_instances", 1, 2, {"created": 1})
        TransferService.interrupt(task.pk, token, "worker_lost")
        return {"created": 2}, {"errors": {"key": "private-late-artifact"}}

    monkeypatch.setattr(TransferExecution, "import_file", late_success)
    TransferExecution.run(task.pk, files=Mock())
    result = TransferService.get(transfer_owner, task.pk)
    assert result.status == "failed" and not result.holds_slot
    assert result.summary["created"] == 1
    assert result.summary["_failure"]["stage"] == "writing_instances"
    assert result.summary["_failure"]["result_uncertain"]
    assert result.artifacts == {}
    assert TransferService.claim(submit(transfer_owner, key="next", kind="import").pk)


def test_queue_timeouts_and_manual_release_trim_history_without_deleting_active_tasks(transfer_owner):
    from datetime import timedelta
    from unittest.mock import Mock

    from django.utils.timezone import now

    from apps.cmdb.models.transfer_task import CmdbTransferTask
    from apps.cmdb.services.transfer_maintenance import TransferMaintenance

    held = submit(transfer_owner, key="held", kind="import")
    token = TransferService.claim(held.pk)
    TransferService.interrupt(held.pk, token, "worker_lost")
    for index in range(5):
        history = submit(transfer_owner, key=f"history-{index}")
        TransferService.cancel(transfer_owner, history.pk)
    queued = [submit(transfer_owner, key=f"queued-{index}") for index in range(5)]
    CmdbTransferTask.objects.filter(pk__in=[task.pk for task in queued]).update(created_at=now() - timedelta(minutes=31))
    TransferMaintenance.maintain(Mock())
    visible = TransferService.list(transfer_owner)
    assert visible.count() == 6
    assert visible.filter(holds_slot=True).count() == 1
    assert not visible.filter(status="queued").exists()
    assert TransferService.reconcile_interrupted(held.pk, verified_stopped=True, summary={"created": 1})
    assert TransferService.list(transfer_owner).count() == 5
    assert not CmdbTransferTask.objects.filter(holds_slot=True).exists()


def test_report_upload_failure_preserves_confirmed_import_counts(transfer_owner, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from apps.cmdb.services.transfer_execution import TransferExecution
    from apps.cmdb.tests.test_transfer_end_to_end import MemoryFiles
    from apps.cmdb.views.transfer_task import task_data

    task = submit(transfer_owner, kind="import", source_key="source", source_hash="hash")
    files = MemoryFiles()
    files.objects["source"] = b"workbook"
    files.put = Mock(side_effect=ConnectionError("PRIVATE-STORAGE-ENDPOINT"))
    context = SimpleNamespace(attrs=[], associations=[])
    monkeypatch.setattr("apps.cmdb.services.transfer_execution.TransferAuthorization.revalidate", Mock(return_value=context))
    monkeypatch.setattr("apps.cmdb.services.transfer_execution.inspect_workbook", Mock(return_value={"sha256": "hash"}))

    def completed_import(task, stream, context, progress):
        summary = {"created": 2, "updated": 0, "failed_rows": 1}
        progress(3, 3, summary, "writing_instances")
        return summary, [(6, "instance", "缺少必填字段")]

    monkeypatch.setattr("apps.cmdb.services.transfer_execution.TransferImport.run", completed_import)
    TransferExecution.run(task.pk, files=files)
    result = TransferService.get(transfer_owner, task.pk)
    data = task_data(result)
    assert result.status == "failed" and not result.holds_slot
    assert data["failure"]["stage"] == "uploading_result"
    assert not data["failure"]["result_uncertain"]
    assert data["summary"] == {"created": 2, "updated": 0, "failed_rows": 1}
    assert data["processed_rows"] == 3
    assert "连接失败" in data["message"]
    assert "PRIVATE-STORAGE-ENDPOINT" not in data["message"]


def test_manual_release_of_legacy_failure_does_not_turn_unknown_counts_into_zero(transfer_owner):
    from apps.cmdb.models.transfer_task import CmdbTransferTask
    from apps.cmdb.views.transfer_task import task_data

    task = submit(transfer_owner, kind="import")
    TransferService.claim(task.pk)
    CmdbTransferTask.objects.filter(pk=task.pk).update(status="interrupted", phase="interrupted", error_code="worker_lost", summary={"created": 0})
    from io import StringIO

    from django.core.management import call_command

    output = StringIO()
    call_command("reconcile_transfer", str(task.pk), verified_stopped=True, note="旧进程已停止", stdout=output)
    assert "任务未重跑" in output.getvalue()
    result = task_data(TransferService.get(transfer_owner, task.pk))
    assert result["summary"]["created"] is None
    assert result["failure"]["result_uncertain"]
    assert not result["failure"]["execution_pending"]
    assert result["available_actions"] == ["delete"]


@pytest.mark.parametrize("verified", [False, True])
def test_manual_release_rejects_unverified_or_non_failed_execution(transfer_owner, verified):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    task = submit(transfer_owner, kind="import")
    TransferService.claim(task.pk)
    with pytest.raises(CommandError):
        call_command("reconcile_transfer", str(task.pk), verified_stopped=verified, note="核实")
    result = TransferService.get(transfer_owner, task.pk)
    assert result.status == "running" and result.holds_slot
