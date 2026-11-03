import pytest

from apps.cmdb.models.collect_task_credential_hit import CollectTaskCredentialHit
from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanFamilyRunProgress, ScanHit, ScanTask
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
    assert list(ScanFamilyRunProgress.objects.filter(family_run=family_run).values_list("host", flat=True)) == ["10.0.1.20"]
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
    assert list(ScanFamilyRunProgress.objects.filter(family_run=family_run).values_list("host", flat=True)) == ["10.0.1.30"]
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
    assert failed["listed"] is True
    assert success["listed"] is True
    assert ScanHit.objects.filter(family_run=family_run).count() == 1
    assert ScanHit.objects.get().credential_id == "cred-2"
    assert ScanHit.objects.get().status == ScanHit.STATUS_SUCCESS
    assert family_run.received_count == 1
    assert list(ScanFamilyRunProgress.objects.filter(family_run=family_run).values_list("host", flat=True)) == ["10.0.1.20"]


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
    assert list(ScanFamilyRunProgress.objects.filter(family_run=family_run).values_list("host", flat=True)) == ["10.0.1.40"]
    delay.assert_called_once_with(family_run.execution_id, "token-nats")


def test_db_auth_failed_upserts_one_placeholder_without_credential():
    family_run = _scan_family_run(target_count=3)
    first = receive_scan_credential_result(
        data={
            "collect_task_id": family_run.id,
            "host": "10.0.1.50",
            "port": 3306,
            "credential_id": "cred-1",
            "status": "failed",
            "error_code": "auth_failed",
        }
    )
    second = receive_scan_credential_result(
        data={
            "collect_task_id": family_run.id,
            "host": "10.0.1.50",
            "port": 3306,
            "credential_id": "cred-2",
            "status": "failed",
            "error_code": "unauthorized",
        }
    )
    assert first["listed"] is True
    assert second["listed"] is True
    hits = list(ScanHit.objects.filter(family_run=family_run))
    assert len(hits) == 1
    assert hits[0].credential_id == ""
    assert hits[0].status == ScanHit.STATUS_FAILED
    assert hits[0].port == 3306
    assert hits[0].error_code == "unauthorized"


def test_port_stage_success_without_credential_writes_low_confidence_hit():
    family_run = _scan_family_run(target_count=4)
    execution = family_run.execution
    response = receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "port",
            "status": "success",
            "host": "10.0.1.60",
            "port": 3306,
            "target_type": "mysql",
        }
    )

    assert response["result"] is True
    assert response["listed"] is True
    hit = ScanHit.objects.get()
    assert hit.execution_id == execution.id
    assert hit.family_run.model_id == "mysql"
    assert hit.family_run.batch_index == 0
    assert hit.host == "10.0.1.60"
    assert hit.port == 3306
    assert hit.credential_id == ""
    assert hit.cmdb_model_id == "mysql"
    assert hit.status == ScanHit.STATUS_SUCCESS
    assert hit.confidence == ScanHit.CONFIDENCE_LOW
    assert "port" in hit.evidence


def test_process_stage_upgrades_same_hit_without_new_row():
    family_run = _scan_family_run(target_count=4)
    execution = family_run.execution
    receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "port",
            "status": "success",
            "host": "10.0.1.60",
            "port": 3306,
            "target_type": "mysql",
        }
    )
    response = receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "process",
            "status": "success",
            "host": "10.0.1.60",
            "port": 3306,
            "target_type": "mysql",
        }
    )

    assert response["listed"] is True
    hits = list(ScanHit.objects.filter(execution=execution))
    assert len(hits) == 1
    hit = hits[0]
    assert hit.credential_id == ""
    assert hit.confidence == ScanHit.CONFIDENCE_MEDIUM
    assert "port" in hit.evidence
    assert "process" in hit.evidence
    assert hit.port == 3306


def test_process_stage_without_listen_port_does_not_invent_fingerprint_port():
    family_run = _scan_family_run(target_count=4)
    execution = family_run.execution
    receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "port",
            "status": "success",
            "host": "10.0.1.60",
            "port": 80,
            "target_type": "nginx",
        }
    )
    response = receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "process",
            "status": "success",
            "host": "10.0.1.60",
            "port": 0,
            "target_type": "mysql",
        }
    )

    assert response["listed"] is True
    mysql_hits = list(ScanHit.objects.filter(execution=execution, cmdb_model_id="mysql"))
    assert len(mysql_hits) == 1
    assert mysql_hits[0].port == 0
    assert mysql_hits[0].confidence == ScanHit.CONFIDENCE_MEDIUM
    assert ScanHit.objects.filter(execution=execution, cmdb_model_id="mysql", port=3306).count() == 0


def test_process_stage_empty_port_upgrades_existing_same_host_model_row():
    family_run = _scan_family_run(target_count=4)
    execution = family_run.execution
    receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "port",
            "status": "success",
            "host": "10.0.1.60",
            "port": 3306,
            "target_type": "mysql",
        }
    )
    response = receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "process",
            "status": "success",
            "host": "10.0.1.60",
            "port": 0,
            "target_type": "mysql",
        }
    )

    assert response["listed"] is True
    hits = list(ScanHit.objects.filter(execution=execution, cmdb_model_id="mysql"))
    assert len(hits) == 1
    assert hits[0].port == 3306
    assert hits[0].confidence == ScanHit.CONFIDENCE_MEDIUM
    assert "process" in hits[0].evidence


def test_collect_stage_failed_does_not_delete_discovery_hit():
    family_run = _scan_family_run(target_count=4)
    execution = family_run.execution
    receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "port",
            "status": "success",
            "host": "10.0.1.60",
            "port": 3306,
            "target_type": "mysql",
        }
    )
    response = receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "collect",
            "status": "failed",
            "host": "10.0.1.60",
            "port": 3306,
            "target_type": "mysql",
            "error_code": "auth_failed",
        }
    )

    assert response["result"] is True
    hit = ScanHit.objects.get()
    assert hit.status == ScanHit.STATUS_SUCCESS
    assert hit.confidence == ScanHit.CONFIDENCE_LOW
    assert "port" in hit.evidence
    assert hit.credential_id == ""


def test_collect_stage_success_upgrades_same_hit_and_records_credential():
    family_run = _scan_family_run(target_count=4)
    execution = family_run.execution
    receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "port",
            "status": "success",
            "host": "10.0.1.60",
            "port": 3306,
            "target_type": "mysql",
        }
    )
    response = receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "collect",
            "status": "success",
            "host": "10.0.1.60",
            "port": 3306,
            "target_type": "mysql",
            "credential_id": "cred-db",
            "snapshot": {"host": "10.0.1.60", "port": 3306, "version": "8.0"},
        }
    )

    assert response["listed"] is True
    hits = list(ScanHit.objects.filter(execution=execution))
    assert len(hits) == 1
    hit = hits[0]
    assert hit.credential_id == "cred-db"
    assert hit.confidence == ScanHit.CONFIDENCE_HIGH
    assert "collect" in hit.evidence
    assert hit.snapshot.get("version") == "8.0"


def test_scan_done_event_marks_schedule_and_kicks_finalize(mocker):
    family_run = _scan_family_run(target_count=3, model_id="host")
    execution = family_run.execution
    execution.schedule = {"scan_admitted": True, "scan_done": False}
    execution.save(update_fields=["schedule"])
    delay = mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.delay")

    response = receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "done",
            "status": "success",
        }
    )

    assert response["result"] is True
    assert response["listed"] is False
    assert ScanHit.objects.count() == 0
    execution.refresh_from_db()
    assert execution.schedule["scan_done"] is True
    assert execution.received_count == 0
    delay.assert_called_once_with(execution.id, "token-nats")


def test_scan_done_event_does_not_complete_when_protocol_pending(mocker):
    family_run = _scan_family_run(target_count=3, model_id="network")
    execution = family_run.execution
    execution.schedule = {"scan_admitted": True}
    execution.save(update_fields=["schedule"])
    delay = mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.delay")

    response = receive_scan_credential_result(
        data={
            "collect_task_id": execution.id,
            "stage": "done",
            "status": "success",
        }
    )

    assert response["result"] is True
    execution.refresh_from_db()
    assert execution.schedule["scan_done"] is True
    delay.assert_not_called()


def test_db_plain_failed_without_auth_code_is_not_listed():
    family_run = _scan_family_run(target_count=2)
    response = receive_scan_credential_result(
        data={
            "collect_task_id": family_run.id,
            "host": "10.0.1.51",
            "port": 3306,
            "status": "failed",
            "error_code": "timeout",
        }
    )
    assert response["listed"] is False
    assert ScanHit.objects.count() == 0
