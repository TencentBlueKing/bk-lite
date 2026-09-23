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
    assert task.status == "interrupted" and task.holds_slot
    dispatch.assert_not_called()


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
