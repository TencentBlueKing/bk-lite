import json

import pytest

from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanHit, ScanTask
from apps.cmdb.services.scan_trigger_service import poll_scan_finalize, trigger_scan_execution
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


def _mark_family_runs_received(execution, *, host_success=()):
    total = 0
    for family_run in execution.family_runs.all():
        family_run.received_count = family_run.target_count
        family_run.save(update_fields=["received_count", "updated_at"])
        total += int(family_run.target_count or 0)
        if family_run.model_id == "host":
            for host in host_success:
                ScanHit.objects.get_or_create(
                    family_run=family_run,
                    host=host,
                    port=22,
                    credential_id="cred-ssh",
                    defaults={
                        "execution": execution,
                        "protocol": "host",
                        "status": ScanHit.STATUS_SUCCESS,
                    },
                )
    execution.received_count = total
    execution.save(update_fields=["received_count", "updated_at"])


def _drain_scan_jobs(execution, mocker, *, host_success=(), max_steps=30):
    mocker.patch("apps.cmdb.services.scan_finalize_service.write_scan_execution", return_value={"status": "written"})
    last = None
    for _ in range(max_steps):
        execution.refresh_from_db()
        if execution.status in {
            ScanExecution.STATUS_COMPLETED,
            ScanExecution.STATUS_FAILED,
            ScanExecution.STATUS_TIMED_OUT,
        }:
            return last
        _mark_family_runs_received(execution, host_success=host_success)
        last = poll_scan_finalize(execution.id, execution.claim_token)
        if last["status"] in {
            ScanExecution.STATUS_COMPLETED,
            ScanExecution.STATUS_FAILED,
            ScanExecution.STATUS_TIMED_OUT,
        }:
            return last
    raise AssertionError("JOB 队列未在预期步数内排空")


def test_trigger_middleware_family_splits_job_types_and_skips_redis_ports(mocker):
    from apps.cmdb.models.collect_model import PortFingerprint
    from apps.cmdb.models.scan_model import SCAN_MIDDLEWARE_TYPES

    mocker.patch("apps.cmdb.services.scan_schedule_service.probe_open_ports", return_value={})
    PortFingerprint.objects.create(port=6379, target_type="redis", protocol="tcp", built_in=False)
    task = _scan_task(
        families=["middleware"],
        credentials={"middleware": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}]},
        cloud_region={"id": 1},
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

    trigger_scan_execution(execution.id)
    admitted = set(ScanFamilyRun.objects.filter(execution=execution).values_list("model_id", flat=True))
    assert len(admitted) == 1
    assert admitted <= set(SCAN_MIDDLEWARE_TYPES)
    assert "middleware" not in admitted
    assert "redis" not in admitted

    _drain_scan_jobs(execution, mocker)
    model_ids = set(ScanFamilyRun.objects.filter(execution=execution).values_list("model_id", flat=True))
    assert model_ids == set(SCAN_MIDDLEWARE_TYPES)
    assert "redis" not in model_ids
    nginx = headers_by_model["nginx"]
    assert nginx.get("cmdbexecutor_type") == "job" or nginx.get("config_type") == "nginx"
    assert nginx.get("cmdbip_precheck") == "True"
    assert "6379" not in json.dumps(headers_by_model)


def test_trigger_middleware_ssh_does_not_use_listen_port(mocker):
    mocker.patch("apps.cmdb.services.scan_schedule_service.probe_open_ports", return_value={})
    task = _scan_task(
        families=["middleware"],
        credentials={"middleware": [{"credential_id": "cred-ssh", "username": "root", "password": "p", "port": 80}]},
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    headers_by_model = {}

    def fake_admit(headers):
        headers_by_model[headers.get("cmdbmodel_id") or headers.get("config_type")] = headers
        return TriggerResult("accepted", 1, 1)

    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=fake_admit,
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")

    trigger_scan_execution(execution.id)
    _drain_scan_jobs(execution, mocker)

    nginx = headers_by_model["nginx"]
    consul = headers_by_model["consul"]
    for headers in (nginx, consul):
        assert headers.get("cmdbport") != "80"
        assert headers.get("cmdbcredential_0_port") != "80"
        assert headers.get("cmdbport") == "22" or headers.get("cmdbcredential_0_port") == "22"


def test_trigger_zero_timeout_sends_positive_job_timeout(mocker):
    from apps.cmdb.services.scan_trigger_service import SCAN_DEFAULT_PLUGIN_TIMEOUT

    mocker.patch("apps.cmdb.services.scan_schedule_service.probe_open_ports", return_value={})
    task = _scan_task(
        families=["middleware"],
        credentials={"middleware": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}]},
        timeout=0,
    )
    execution = ScanExecution.objects.create(task=task)
    captured = []

    def fake_admit(headers):
        captured.append(headers)
        return TriggerResult("accepted", 1, 1)

    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=fake_admit,
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")

    trigger_scan_execution(execution.id)

    assert captured
    timeouts = [float(h.get("cmdbtimeout") or h.get("timeout") or 0) for h in captured]
    assert all(t > 0 for t in timeouts)
    assert timeouts[0] == float(SCAN_DEFAULT_PLUGIN_TIMEOUT)


def test_trigger_empty_middleware_pool_admits_agent_placeholder(mocker):
    mocker.patch("apps.cmdb.services.scan_schedule_service.probe_open_ports", return_value={})
    task = _scan_task(
        families=["middleware"],
        credentials={"middleware": []},
        cloud_region={"id": 1, "name": "default"},
    )
    execution = ScanExecution.objects.create(task=task)
    admit = mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        return_value=TriggerResult("accepted", 1, 1),
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")

    result = trigger_scan_execution(execution.id)
    assert admit.call_count == 1
    assert result["target_count"] == 1
    assert ScanFamilyRun.objects.filter(execution=execution, admit_status=ScanFamilyRun.ADMIT_FAILED).count() == 0
    first_call = admit.call_args_list[0]
    first_headers = first_call.args[0] if first_call.args else first_call.kwargs.get("headers")
    assert "agent" in json.dumps(first_headers)


def test_trigger_empty_host_pool_admits_agent_placeholder(mocker):
    task = _scan_task(
        families=["host"],
        credentials={"host": []},
        cloud_region={"id": 1, "name": "default"},
    )
    execution = ScanExecution.objects.create(task=task)
    admit = mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        return_value=TriggerResult("accepted", 1, 1),
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    trigger_scan_execution(execution.id)
    assert admit.call_count == 1
    assert ScanFamilyRun.objects.get(execution=execution, model_id="host").admit_status != ScanFamilyRun.ADMIT_FAILED


def test_trigger_incomplete_middleware_ssh_reuses_host_secret(mocker):
    mocker.patch("apps.cmdb.services.scan_schedule_service.probe_open_ports", return_value={})
    task = _scan_task(
        families=["host", "middleware"],
        credentials={
            "host": [{"credential_id": "cred-host", "username": "root", "password": "host-secret", "port": 22}],
            "middleware": [{"credential_id": "cred-mw", "username": "root", "port": 80}],
        },
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    seen = []

    def fake_admit(headers):
        seen.append(headers)
        return TriggerResult("accepted", 1, 1)

    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=fake_admit,
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    trigger_scan_execution(execution.id)
    _drain_scan_jobs(execution, mocker, host_success=["10.0.1.1"])
    nginx = [h for h in seen if (h.get("cmdbmodel_id") or h.get("config_type")) == "nginx"][0]
    assert nginx.get("cmdbport") == "22" or nginx.get("cmdbcredential_0_port") == "22"
    assert nginx.get("cmdbpassword")
    assert nginx.get("cmdbport") != "80"
    assert nginx.get("cmdbcredential_0_port") != "80"


def test_trigger_middleware_reuses_host_ssh_pool(mocker):
    mocker.patch("apps.cmdb.services.scan_schedule_service.probe_open_ports", return_value={})
    task = _scan_task(
        families=["host", "middleware"],
        credentials={"host": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}]},
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    seen = []

    def fake_admit(headers):
        seen.append(headers)
        return TriggerResult("accepted", 1, 1)

    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=fake_admit,
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    trigger_scan_execution(execution.id)
    first_model = seen[0].get("cmdbmodel_id") or seen[0].get("config_type")
    assert first_model == "host"
    assert not [h for h in seen if (h.get("cmdbmodel_id") or h.get("config_type")) == "nginx"]

    _drain_scan_jobs(execution, mocker, host_success=["10.0.1.1"])
    nginx_headers = [h for h in seen if (h.get("cmdbmodel_id") or h.get("config_type")) == "nginx"][0]
    assert "root" in json.dumps(nginx_headers)


def test_trigger_network_defaults_missing_snmp_version(mocker):
    task = _scan_task(
        families=["network"],
        credentials={
            "network": [
                {"community": "public", "snmp_port": "161"},
                {"version": "v3", "username": "u", "level": "authNoPriv", "integrity": "sha", "authkey": "authkey12"},
            ]
        },
    )
    execution = ScanExecution.objects.create(task=task)
    captured = []

    def fake_admit(headers):
        captured.append(headers)
        return TriggerResult("accepted", 1, 1)

    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=fake_admit,
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")

    trigger_scan_execution(execution.id)

    assert captured
    headers = captured[0]
    assert headers.get("cmdbcredential_0_version") == "v2"
    assert headers.get("cmdbcredential_1_version") == "v3"


def test_trigger_network_plus_host_admits_protocol_first(mocker):
    task = _scan_task(
        families=["network", "host"],
        credentials={
            "network": [{"version": "v2c", "community": "public"}],
            "host": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}],
        },
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    admit = mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        return_value=TriggerResult("accepted", 3, 3),
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")

    result = trigger_scan_execution(execution.id)

    assert admit.call_count == 1
    assert result["target_count"] == 3
    assert set(ScanFamilyRun.objects.filter(execution=execution).values_list("model_id", flat=True)) == {"network"}


def test_poll_does_not_complete_while_job_queue_pending(mocker):
    task = _scan_task(
        families=["network", "host"],
        credentials={
            "network": [{"version": "v2c", "community": "public"}],
            "host": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}],
        },
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        return_value=TriggerResult("accepted", 3, 3),
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    mocker.patch("apps.cmdb.services.scan_finalize_service.write_scan_execution", return_value={"status": "written"})
    trigger_scan_execution(execution.id)
    execution.refresh_from_db()
    _mark_family_runs_received(execution)

    result = poll_scan_finalize(execution.id, execution.claim_token)

    assert result["status"] == "waiting"
    execution.refresh_from_db()
    assert execution.status == ScanExecution.STATUS_RUNNING
    assert ScanFamilyRun.objects.filter(execution=execution, model_id="host").exists()


def test_poll_host_job_skips_snmp_success_ips(mocker):
    from apps.cmdb.models.scan_model import ScanHit as Hit

    task = _scan_task(
        families=["network", "host"],
        credentials={
            "network": [{"version": "v2c", "community": "public"}],
            "host": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}],
        },
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    captured = []

    def fake_admit(headers):
        captured.append(headers)
        return TriggerResult("accepted", 2, 2)

    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=fake_admit,
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    trigger_scan_execution(execution.id)
    execution.refresh_from_db()
    network_run = ScanFamilyRun.objects.get(execution=execution, model_id="network")
    Hit.objects.create(
        execution=execution,
        family_run=network_run,
        protocol="snmp",
        host="10.0.1.1",
        port=161,
        credential_id="cred-snmp",
        status=Hit.STATUS_SUCCESS,
    )
    _mark_family_runs_received(execution)
    poll_scan_finalize(execution.id, execution.claim_token)

    host_headers = [h for h in captured if (h.get("cmdbmodel_id") or h.get("config_type")) == "host"][0]
    hosts = host_headers.get("cmdbhosts") or ""
    assert "10.0.1.1" not in hosts
    assert "10.0.1.2" in hosts
    assert "10.0.1.3" in hosts
    assert host_headers.get("cmdbip_precheck") == "True"


def test_poll_protocol_deadline_starts_job_instead_of_dropping_queue(mocker):
    from datetime import timedelta

    from django.utils.timezone import now

    task = _scan_task(
        families=["network", "host"],
        credentials={
            "network": [{"version": "v2c", "community": "public"}],
            "host": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}],
        },
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        return_value=TriggerResult("accepted", 3, 3),
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    mocker.patch("apps.cmdb.services.scan_finalize_service.write_scan_execution", return_value={"status": "written"})
    trigger_scan_execution(execution.id)
    execution.refresh_from_db()
    execution.deadline_at = now() - timedelta(seconds=1)
    execution.save(update_fields=["deadline_at"])

    result = poll_scan_finalize(execution.id, execution.claim_token)

    assert result["status"] != ScanExecution.STATUS_TIMED_OUT
    assert ScanFamilyRun.objects.filter(execution=execution, model_id="host").exists()


def test_poll_chunks_host_jobs_and_admits_next_batch(mocker):
    mocker.patch("apps.cmdb.services.scan_schedule_service.SCAN_JOB_BATCH_SIZE", 2)
    task = _scan_task(
        families=["host"],
        credentials={"host": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}]},
        cloud_region={"id": 1},
        ip_ranges=[{"begin": "10.0.1.1", "end": "10.0.1.3"}],
    )
    execution = ScanExecution.objects.create(task=task)
    captured = []

    def fake_admit(headers):
        captured.append(headers)
        return TriggerResult("accepted", 2, 2)

    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=fake_admit,
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    mocker.patch("apps.cmdb.services.scan_finalize_service.write_scan_execution", return_value={"status": "written"})
    trigger_scan_execution(execution.id)
    execution.refresh_from_db()
    assert ScanFamilyRun.objects.filter(execution=execution, model_id="host").count() == 1
    first_hosts = captured[0].get("cmdbhosts") or ""
    assert "10.0.1.3" not in first_hosts

    _mark_family_runs_received(execution)
    poll_scan_finalize(execution.id, execution.claim_token)
    assert ScanFamilyRun.objects.filter(execution=execution, model_id="host").count() == 2
    second_hosts = captured[1].get("cmdbhosts") or ""
    assert "10.0.1.3" in second_hosts


def test_poll_middleware_port_probe_keeps_matching_types_only(mocker):
    mocker.patch(
        "apps.cmdb.services.scan_schedule_service.probe_open_ports",
        return_value={"10.0.1.2": [80]},
    )
    task = _scan_task(
        families=["middleware"],
        credentials={"middleware": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}]},
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        return_value=TriggerResult("accepted", 1, 1),
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    mocker.patch("apps.cmdb.services.scan_finalize_service.write_scan_execution", return_value={"status": "written"})
    trigger_scan_execution(execution.id)
    _drain_scan_jobs(execution, mocker)
    model_ids = set(ScanFamilyRun.objects.filter(execution=execution).values_list("model_id", flat=True))
    assert model_ids == {"nginx"}
