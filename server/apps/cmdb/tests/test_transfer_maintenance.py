from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils.timezone import now

from apps.cmdb.models.transfer_task import CmdbTransferTask
from apps.cmdb.services.transfer_maintenance import TransferMaintenance
from apps.cmdb.services.transfer_service import TransferService
from apps.cmdb.tests.test_transfer_service import submit


@pytest.mark.django_db
def test_cleanup_retries_failed_file_deletion_and_protects_active_files(transfer_owner):
    task = submit(transfer_owner)
    TransferService.cancel(transfer_owner, task.pk)
    CmdbTransferTask.objects.filter(pk=task.pk).update(expires_at=now() - timedelta(seconds=1), source_key="transfer/tmp/a/source.xlsx")
    files = Mock()
    files.scan.return_value = []
    files.delete.side_effect = OSError("private-sentinel")
    TransferMaintenance.cleanup(files)
    assert CmdbTransferTask.objects.filter(pk=task.pk).exists()
    files.delete.side_effect = None
    TransferMaintenance.cleanup(files)
    assert not CmdbTransferTask.objects.filter(pk=task.pk).exists()
    active = submit(transfer_owner, key="active")
    TransferService.claim(active.pk)
    CmdbTransferTask.objects.filter(pk=active.pk).update(expires_at=now() - timedelta(days=1))
    TransferMaintenance.cleanup(files)
    assert CmdbTransferTask.objects.filter(pk=active.pk).exists()


@pytest.mark.django_db
def test_watchdog_does_not_replay_uncertain_import(transfer_owner):
    task = submit(transfer_owner, kind="import")
    TransferService.claim(task.pk)
    CmdbTransferTask.objects.filter(pk=task.pk).update(lease_expires_at=now() - timedelta(seconds=1))
    dispatch = Mock()
    TransferMaintenance.maintain(dispatch)
    task.refresh_from_db()
    assert task.status == "failed" and task.holds_slot
    dispatch.assert_not_called()


@pytest.mark.django_db
def test_hard_limit_grace_releases_dead_slot_without_replaying(transfer_owner, caplog):
    import logging

    expired = submit(transfer_owner, key="expired", kind="import")
    token = TransferService.claim(expired.pk)
    TransferService.progress(expired.pk, token, "writing_instances", 1, 4, {"created": 1, "updated": 0, "failed_rows": 0})
    TransferService.interrupt(expired.pk, token, "worker_lost")
    recent = submit(transfer_owner, key="recent", kind="import", model_id="mysql")
    recent_token = TransferService.claim(recent.pk)
    TransferService.interrupt(recent.pk, recent_token, "worker_lost")
    CmdbTransferTask.objects.filter(pk=expired.pk).update(
        started_at=now() - timedelta(minutes=19),
        filename="SECRET-FILENAME-SENTINEL",
        message="SECRET-MESSAGE-SENTINEL",
    )
    CmdbTransferTask.objects.filter(pk=recent.pk).update(started_at=now() - timedelta(minutes=17))
    send = Mock()
    with caplog.at_level(logging.INFO, logger="cmdb"):
        TransferMaintenance.maintain(send)
    expired.refresh_from_db()
    recent.refresh_from_db()
    assert expired.status == "failed" and not expired.holds_slot
    assert expired.summary["created"] == 1
    assert expired.summary["_failure"]["stage"] == "writing_instances"
    assert expired.summary["_failure"]["result_uncertain"]
    assert expired.message == "执行已超过进程时限，占用已解除；已写入数据保留，未自动重跑"
    assert recent.status == "failed" and recent.holds_slot
    send.assert_not_called()
    assert TransferService.claim(submit(transfer_owner, key="same-model", kind="import", model_id="mysql").pk) is None
    assert TransferService.claim(submit(transfer_owner, key="next", kind="import").pk)
    records = [record for record in caplog.records if record.msg == "event=cmdb_transfer_slot_released task_id=%s failed_stage=%s error_type=%s"]
    assert len(records) == 1
    assert records[0].args == (str(expired.pk), "writing_instances", "ExecutionHardLimit")
    rendered = logging.Formatter().format(records[0])
    assert str(expired.pk) in records[0].getMessage()
    assert "SECRET-FILENAME-SENTINEL" not in rendered
    assert "SECRET-MESSAGE-SENTINEL" not in rendered


def test_broker_failure_is_recovered_without_creating_another_task(transfer_owner, caplog):
    task = submit(transfer_owner)
    send = Mock(side_effect=OSError("PRIVATE-BROKER-SENTINEL"))
    TransferMaintenance.dispatch(task.pk, send)
    assert TransferService.get(transfer_owner, task.pk).status == "queued"
    assert "PRIVATE-BROKER-SENTINEL" not in caplog.text
    TransferMaintenance.dispatch(task.pk, send)
    assert send.call_count == 1
    CmdbTransferTask.objects.filter(pk=task.pk).update(dispatched_at=now() - timedelta(minutes=2))
    send.side_effect = None
    TransferMaintenance.maintain(send)
    assert send.call_count == 2
    assert TransferService.list(transfer_owner).count() == 1


def test_orphan_scan_respects_active_task_and_age(transfer_owner):
    from types import SimpleNamespace

    task = submit(transfer_owner, source_key="transfer/tmp/active/source.xlsx")
    files = Mock()
    old = now() - timedelta(days=2)
    files.scan.return_value = [
        SimpleNamespace(object_name=task.source_key, last_modified=old),
        SimpleNamespace(object_name=f"transfer/{transfer_owner.pk}/{task.pk}/old/result.xlsx", last_modified=old),
        SimpleNamespace(object_name="transfer/tmp/orphan/source.xlsx", last_modified=old),
        SimpleNamespace(object_name="transfer/tmp/new/source.xlsx", last_modified=now()),
    ]
    TransferMaintenance.cleanup(files)
    files.delete.assert_called_once_with("transfer/tmp/orphan/source.xlsx")


def test_broker_outage_stops_batch_publish_but_still_expires_old_queue(transfer_owner):
    from apps.system_mgmt.models.user import User

    first = submit(transfer_owner)
    second_owner = User.objects.create(username="transfer-second", domain=transfer_owner.domain)
    second = submit(second_owner)
    old_owner = User.objects.create(username="transfer-old", domain=transfer_owner.domain)
    old = submit(old_owner)
    CmdbTransferTask.objects.filter(pk=old.pk).update(created_at=now() - timedelta(minutes=31))
    send = Mock(side_effect=OSError("BROKER-OFFLINE-SENTINEL"))
    TransferMaintenance.maintain(send)
    assert send.call_count == 1
    assert TransferService.get(transfer_owner, first.pk).status == "queued"
    assert TransferService.get(second_owner, second.pk).dispatched_at is None
    assert TransferService.get(old_owner, old.pk).status == "failed"
