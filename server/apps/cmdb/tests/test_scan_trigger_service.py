import json

import pytest

from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanTask
from apps.cmdb.services.scan_trigger_service import trigger_scan_execution
from apps.cmdb.services.stargazer_collect_trigger import StargazerCollectPermanentError, TriggerResult

pytestmark = pytest.mark.django_db


def _scan_task(**overrides):
    values = {
        "name": "scan-trigger",
        "team": ["1"],
        "families": ["mysql", "network"],
        "ip_ranges": [{"begin": "10.0.1.1", "end": "10.0.1.3"}],
        "access_point": [{"id": "node-1"}],
        "credentials": {
            "mysql": [{"username": "u", "password": "p", "port": 3306}],
            "network": [{"version": "v2c", "community": "public"}],
        },
        "timeout": 30,
    }
    values.update(overrides)
    return ScanTask.objects.create(**values)


def test_trigger_scan_admits_each_family_and_schedules_finalize(mocker):
    task = _scan_task()
    execution = ScanExecution.objects.create(task=task)
    admit = mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=[TriggerResult("accepted", 3, 3), TriggerResult("accepted", 3, 3)],
    )
    apply_async = mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    push = mocker.patch("apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params")

    result = trigger_scan_execution(execution.id)

    assert result["target_count"] == 6
    assert admit.call_count == 2
    execution.refresh_from_db()
    assert execution.status == ScanExecution.STATUS_RUNNING
    assert execution.claim_token
    assert execution.target_count == 6
    assert execution.deadline_at is not None
    assert execution.family_runs.count() == 2
    apply_async.assert_called_once()
    assert apply_async.call_args.kwargs["countdown"] == 30
    push.assert_not_called()


def test_trigger_scan_continues_other_families_when_one_admit_fails(mocker):
    task = _scan_task()
    execution = ScanExecution.objects.create(task=task)
    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=[
            StargazerCollectPermanentError("mysql down"),
            TriggerResult("accepted", 4, 4),
        ],
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")

    result = trigger_scan_execution(execution.id)

    assert result["target_count"] == 4
    statuses = set(ScanFamilyRun.objects.filter(execution=execution).values_list("admit_status", flat=True))
    assert ScanFamilyRun.ADMIT_FAILED in statuses
    assert ScanFamilyRun.ADMIT_ACCEPTED in statuses


def test_finalize_with_stale_token_does_not_mutate(mocker):
    from apps.cmdb.tasks.celery_tasks import finalize_scan_execution

    task = _scan_task(name="scan-fence")
    execution = ScanExecution.objects.create(
        task=task,
        status=ScanExecution.STATUS_RUNNING,
        claim_token="token-new",
        target_count=2,
    )
    result = finalize_scan_execution.run(execution.id, "token-old")
    assert result["status"] == "stale"
    execution.refresh_from_db()
    assert execution.status == ScanExecution.STATUS_RUNNING
    assert execution.claim_token == "token-new"


def test_trigger_database_family_splits_catalog_ports_and_skips_middleware(mocker):
    from apps.cmdb.models.collect_model import PortFingerprint
    from apps.cmdb.services.port_fingerprint import sync_builtin_port_fingerprints

    sync_builtin_port_fingerprints()
    PortFingerprint.objects.create(port=3307, target_type="mysql", protocol="tcp", built_in=False)
    PortFingerprint.objects.create(port=6379, target_type="redis", protocol="tcp", built_in=False)
    task = _scan_task(
        families=["database", "network"],
        credentials={
            "database": [{"credential_id": "cred-db", "username": "u", "password": "p"}],
            "network": [{"version": "v2c", "community": "public"}],
        },
    )
    execution = ScanExecution.objects.create(task=task)
    headers_by_model = {}

    def fake_admit(headers):
        headers_by_model[headers.get("cmdbmodel_id") or headers.get("config_type")] = headers
        return TriggerResult("accepted", 2, 2)

    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=fake_admit,
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")

    result = trigger_scan_execution(execution.id)

    model_ids = set(ScanFamilyRun.objects.filter(execution=execution).values_list("model_id", flat=True))
    assert model_ids == {"mysql", "postgresql", "mssql", "network"}
    assert "database" not in model_ids
    mysql_headers = headers_by_model["mysql"]
    mysql_ports = {
        mysql_headers.get("cmdbcredential_0_port"),
        mysql_headers.get("cmdbcredential_1_port"),
    }
    assert mysql_ports == {"3306", "3307"}
    assert "6379" not in json.dumps(mysql_headers)
    assert result["target_count"] == 8


def test_trigger_database_family_skips_sql_when_catalog_empty(mocker):
    from apps.cmdb.models.collect_model import PortFingerprint

    PortFingerprint.objects.all().delete()
    task = _scan_task(
        families=["database", "network"],
        credentials={
            "database": [{"username": "u", "password": "p"}],
            "network": [{"version": "v2c", "community": "public"}],
        },
    )
    execution = ScanExecution.objects.create(task=task)
    admit = mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        return_value=TriggerResult("accepted", 3, 3),
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")

    trigger_scan_execution(execution.id)

    assert admit.call_count == 1
    assert set(ScanFamilyRun.objects.filter(execution=execution).values_list("model_id", flat=True)) == {"network"}
