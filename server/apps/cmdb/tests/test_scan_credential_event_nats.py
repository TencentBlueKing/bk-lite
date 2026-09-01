import pytest

from apps.cmdb.models.collect_task_credential_hit import CollectTaskCredentialHit
from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanHit, ScanTask
from apps.cmdb.nats.nats import receive_scan_credential_result

pytestmark = pytest.mark.django_db


def _scan_family_run(*, target_count=2, model_id="mysql"):
    task = ScanTask.objects.create(
        name="scan-nats",
        team=["1"],
        families=[model_id],
        access_point=[{"id": "node-1"}],
    )
    execution = ScanExecution.objects.create(
        task=task,
        status=ScanExecution.STATUS_RUNNING,
        claim_token="token-nats",
        target_count=target_count,
    )
    return ScanFamilyRun.objects.create(
        execution=execution,
        model_id=model_id,
        driver_type="protocol",
        target_count=target_count,
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )


def test_scan_success_writes_hit_not_collect_credential_hit(mocker):
    family_run = _scan_family_run(target_count=1)
    delay = mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.delay")

    response = receive_scan_credential_result(
        data={
            "collect_task_id": family_run.id,
            "host": "10.0.1.20",
            "credential_id": "cred-db",
            "status": "success",
            "snapshot": {"sysobjectid": "1.3.6.1.4.1.9.1.1", "port": 3306},
        }
    )

    assert response["result"] is True
    assert response["listed"] is True
    assert CollectTaskCredentialHit.objects.count() == 0
    hit = ScanHit.objects.get()
    assert hit.host == "10.0.1.20"
    assert hit.credential_id == "cred-db"
    assert hit.status == ScanHit.STATUS_SUCCESS
    assert hit.soid == "1.3.6.1.4.1.9.1.1"
    assert hit.port == 3306
    family_run.refresh_from_db()
    assert family_run.received_count == 1
    assert family_run.progress_hosts == ["10.0.1.20"]
    delay.assert_called_once_with(family_run.execution_id, "token-nats")


def test_scan_unreachable_counts_progress_without_hit():
    family_run = _scan_family_run(target_count=3)
    response = receive_scan_credential_result(
        data={
            "collect_task_id": family_run.id,
            "host": "10.0.1.30",
            "status": "unreachable",
        }
    )
    assert response["result"] is True
    assert response["listed"] is False
    assert ScanHit.objects.count() == 0
    family_run.refresh_from_db()
    assert family_run.received_count == 1
    assert family_run.progress_hosts == ["10.0.1.30"]
    family_run.execution.refresh_from_db()
    assert family_run.execution.received_count == 1


def test_scan_failed_counts_progress_success_lists_once():
    family_run = _scan_family_run(target_count=5)
    failed = receive_scan_credential_result(
        data={
            "collect_task_id": family_run.id,
            "host": "10.0.1.20",
            "credential_id": "cred-1",
            "status": "failed",
            "error_code": "auth_failed",
        }
    )
    success = receive_scan_credential_result(
        data={
            "collect_task_id": family_run.id,
            "host": "10.0.1.20",
            "credential_id": "cred-2",
            "status": "success",
        }
    )
    family_run.refresh_from_db()
    assert failed["listed"] is False
    assert success["listed"] is True
    assert ScanHit.objects.filter(family_run=family_run).count() == 1
    assert ScanHit.objects.get().credential_id == "cred-2"
    assert family_run.received_count == 1
    assert family_run.progress_hosts == ["10.0.1.20"]


def test_scan_credentials_exhausted_without_credential_id_counts_progress(mocker):
    family_run = _scan_family_run(target_count=1)
    delay = mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.delay")

    response = receive_scan_credential_result(
        data={
            "collect_task_id": family_run.id,
            "host": "10.0.1.40",
            "credential_id": "-",
            "status": "failed",
            "error_code": "credentials_exhausted",
            "event_version": "2",
            # 故意缺 finished_at 等身份字段：扫描失败仍应计进度
        }
    )

    assert response["result"] is True
    assert response["listed"] is False
    assert ScanHit.objects.count() == 0
    family_run.refresh_from_db()
    assert family_run.received_count == 1
    assert family_run.progress_hosts == ["10.0.1.40"]
    delay.assert_called_once_with(family_run.execution_id, "token-nats")
