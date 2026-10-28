import importlib
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.db import connection

from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanFamilyRunProgress, ScanHit, ScanTask
from apps.cmdb.services.scan_credential_result_service import ScanCredentialResultService

pytestmark = pytest.mark.django_db

HOST_COUNT = 32
QUADRATIC_LIST_ELEMENTS = HOST_COUNT * (HOST_COUNT + 1) // 2


def _network_family_run():
    task = ScanTask.objects.create(
        name="scan-progress-growth",
        team=["1"],
        families=["network"],
        access_point=[{"id": "node-1"}],
    )
    execution = ScanExecution.objects.create(
        task=task,
        status=ScanExecution.STATUS_RUNNING,
        claim_token="token-progress",
        target_count=HOST_COUNT + 1,
    )
    return ScanFamilyRun.objects.create(
        execution=execution,
        model_id="network",
        driver_type="protocol",
        target_count=HOST_COUNT + 1,
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )


def _unreachable(family_run, host):
    return ScanCredentialResultService.process_result(
        {
            "collect_task_id": family_run.id,
            "host": host,
            "status": "unreachable",
        }
    )


def test_unreachable_hosts_add_one_progress_row_without_rewriting_the_list(monkeypatch):
    written_elements = 0
    original_save = ScanFamilyRun.save

    def counting_save(self, *args, **kwargs):
        nonlocal written_elements
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "progress_hosts" in update_fields:
            written_elements += len(list(self.progress_hosts or []))
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(ScanFamilyRun, "save", counting_save)

    family_run = _network_family_run()
    hosts = [f"10.8.0.{index}" for index in range(1, HOST_COUNT + 1)]
    for host in hosts:
        response = _unreachable(family_run, host)
        assert response["result"] is True
        assert response["listed"] is False

    assert written_elements == 0, (
        f"progress_hosts rewrote {written_elements} list elements; "
        f"{HOST_COUNT} new hosts must not accumulate {QUADRATIC_LIST_ELEMENTS}"
    )

    family_run.refresh_from_db()
    family_run.execution.refresh_from_db()
    assert family_run.progress_hosts == []
    assert family_run.received_count == HOST_COUNT
    assert family_run.execution.received_count == HOST_COUNT
    assert ScanHit.objects.filter(family_run=family_run).count() == 0
    assert ScanFamilyRunProgress.objects.filter(family_run=family_run).count() == HOST_COUNT
    assert set(ScanFamilyRunProgress.objects.filter(family_run=family_run).values_list("host", flat=True)) == set(hosts)

    repeated = _unreachable(family_run, hosts[0])
    assert repeated["result"] is True
    assert repeated["listed"] is False
    family_run.refresh_from_db()
    family_run.execution.refresh_from_db()
    assert family_run.received_count == HOST_COUNT
    assert family_run.execution.received_count == HOST_COUNT
    assert ScanFamilyRunProgress.objects.filter(family_run=family_run).count() == HOST_COUNT
    assert ScanHit.objects.filter(family_run=family_run).count() == 0


def _family_run_with_progress(task, *, status, hosts, received_count):
    execution = ScanExecution.objects.create(
        task=task,
        status=status,
        claim_token=f"token-{status}",
        target_count=received_count,
        received_count=received_count,
    )
    return ScanFamilyRun.objects.create(
        execution=execution,
        model_id="network",
        driver_type="protocol",
        target_count=received_count,
        received_count=received_count,
        progress_hosts=list(hosts),
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )


def test_backfill_copies_only_open_executions_without_changing_counts():
    task = ScanTask.objects.create(
        name="scan-progress-backfill",
        team=["1"],
        families=["network"],
        access_point=[{"id": "node-1"}],
    )
    long_host = "n" * 70
    open_hosts = ["10.9.0.1", "10.9.0.1", "", "10.9.0.2", long_host]
    open_runs = [
        _family_run_with_progress(task, status=status, hosts=open_hosts, received_count=3)
        for status in (
            ScanExecution.STATUS_PENDING,
            ScanExecution.STATUS_RUNNING,
            ScanExecution.STATUS_FINALIZING,
        )
    ]
    closed_runs = [
        _family_run_with_progress(task, status=status, hosts=["10.9.9.9"], received_count=1)
        for status in (
            ScanExecution.STATUS_COMPLETED,
            ScanExecution.STATUS_FAILED,
            ScanExecution.STATUS_TIMED_OUT,
        )
    ]

    copy_open_progress_hosts = importlib.import_module("apps.cmdb.migrations.0062_scan_family_run_progress").copy_open_progress_hosts
    schema_editor = SimpleNamespace(connection=connection)
    copy_open_progress_hosts(django_apps, schema_editor)
    copy_open_progress_hosts(django_apps, schema_editor)

    expected_hosts = {"10.9.0.1", "10.9.0.2", "n" * 64}
    for run in open_runs:
        run.refresh_from_db()
        run.execution.refresh_from_db()
        assert run.received_count == 3
        assert run.execution.received_count == 3
        assert run.progress_hosts == open_hosts
        assert set(ScanFamilyRunProgress.objects.filter(family_run=run).values_list("host", flat=True)) == expected_hosts
    for run in closed_runs:
        run.refresh_from_db()
        run.execution.refresh_from_db()
        assert run.received_count == 1
        assert run.execution.received_count == 1
        assert run.progress_hosts == ["10.9.9.9"]
        assert ScanFamilyRunProgress.objects.filter(family_run=run).count() == 0
