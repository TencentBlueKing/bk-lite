import pytest

from apps.cmdb.models.scan_model import SCAN_MIDDLEWARE_TYPES, ScanExecution, ScanFamilyRun, ScanTask
from apps.cmdb.services.port_fingerprint import sync_builtin_port_fingerprints
from apps.cmdb.services.process_fingerprint import sync_builtin_process_fingerprints
from apps.cmdb.services.scan_trigger_service import poll_scan_finalize, trigger_scan_execution
from apps.cmdb.services.stargazer_collect_trigger import TriggerResult

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


def _patch_stargazer(mocker, *, scan_total=3, admit=None, scan_side_effect=None):
    scan = mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit_scan_discover",
        side_effect=scan_side_effect,
        return_value=None if scan_side_effect else TriggerResult("accepted", scan_total, scan_total),
    )
    protocol = mocker.patch(
        "apps.cmdb.services.scan_trigger_service.StargazerCollectTriggerClient.admit",
        side_effect=admit,
        return_value=None if admit else TriggerResult("accepted", scan_total, scan_total),
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.finalize_scan_execution.apply_async")
    return scan, protocol


def test_trigger_scan_admits_discover_and_network(mocker):
    sync_builtin_port_fingerprints()
    task = _scan_task()
    execution = ScanExecution.objects.create(task=task)
    scan, admit = _patch_stargazer(mocker, scan_total=3)
    mocker.patch("apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params")

    result = trigger_scan_execution(execution.id)

    assert result["target_count"] == 3
    scan.assert_called_once()
    assert admit.call_count == 1
    body = scan.call_args.args[0]
    types = {item["target_type"] for item in body["port_fingerprints"]}
    assert "mysql" in types
    assert "nginx" in types
    execution.refresh_from_db()
    assert execution.status == ScanExecution.STATUS_RUNNING
    assert execution.target_count == 3
    assert ScanFamilyRun.objects.filter(execution=execution, model_id="network").exists()
    assert not ScanFamilyRun.objects.filter(execution=execution, model_id="mysql").exists()


def test_trigger_host_only_puts_host_collect_creds(mocker):
    sync_builtin_port_fingerprints()
    task = _scan_task(
        families=["host"],
        credentials={"host": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}]},
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    scan, admit = _patch_stargazer(mocker, scan_total=3)

    trigger_scan_execution(execution.id)

    admit.assert_not_called()
    body = scan.call_args.args[0]
    assert "host" in body["collect_credentials"]
    assert body["host_login"]["execution_id"] == execution.id
    assert body["skip_hosts"] == []


def test_trigger_influx_uses_collect_creds_not_protocol_admit(mocker):
    sync_builtin_port_fingerprints()
    task = _scan_task(
        families=["influxdb"],
        credentials={"influxdb": [{"credential_id": "cred-inf", "token": "t", "port": 8086}]},
    )
    execution = ScanExecution.objects.create(task=task)
    scan, admit = _patch_stargazer(mocker, scan_total=3)

    trigger_scan_execution(execution.id)

    admit.assert_not_called()
    body = scan.call_args.args[0]
    assert "influxdb" in body["collect_credentials"]
    assert body["collect_credentials"]["influxdb"][0]["token"] == "t"


def test_get_nodes_by_ips_accepts_scan_execution_id(mocker):
    from apps.node_mgmt.nats import node as node_nats
    from apps.node_mgmt.services.node import NodeService

    task = _scan_task()
    execution = ScanExecution.objects.create(task=task)
    captured = {}

    def query(ips, **context):
        captured.update(ips=ips, context=context)
        return {"nodes": []}

    mocker.patch.object(NodeService, "get_nodes_by_ips", query)
    result = node_nats.get_nodes_by_ips(
        {
            "ips": ["10.0.0.1"],
            "collect_task_id": execution.id,
            "cloud_region_id": 7,
        }
    )
    assert result == {"nodes": []}
    assert captured["context"]["organization_ids"]
    assert captured["context"]["cloud_region_id"] == 7


def test_trigger_host_only_still_sends_fingerprint_types(mocker):
    sync_builtin_port_fingerprints()
    sync_builtin_process_fingerprints()
    task = _scan_task(
        families=["host"],
        credentials={"host": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}]},
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    scan, admit = _patch_stargazer(mocker, scan_total=3)

    trigger_scan_execution(execution.id)

    scan.assert_called_once()
    admit.assert_not_called()
    body = scan.call_args.args[0]
    types = {item["target_type"] for item in body["port_fingerprints"]}
    assert "mysql" in types
    assert "nginx" in types
    assert body.get("host_login")
    assert "nginx_info" not in str(body)


def test_trigger_without_host_login_still_admits_port_stage(mocker):
    sync_builtin_port_fingerprints()
    task = _scan_task(families=["network"], credentials={"network": [{"version": "v2c", "community": "public"}]})
    execution = ScanExecution.objects.create(task=task)
    scan, admit = _patch_stargazer(mocker, scan_total=3)

    trigger_scan_execution(execution.id)

    body = scan.call_args.args[0]
    assert not body.get("host_login")
    admit.assert_called_once()


def test_trigger_database_selected_puts_sql_creds_and_skips_mysql_info(mocker):
    sync_builtin_port_fingerprints()
    task = _scan_task(
        families=["database"],
        credentials={"database": [{"credential_id": "cred-db", "username": "u", "password": "p"}]},
    )
    execution = ScanExecution.objects.create(task=task)
    scan, admit = _patch_stargazer(mocker, scan_total=3)

    trigger_scan_execution(execution.id)

    admit.assert_not_called()
    body = scan.call_args.args[0]
    assert "mysql" in body["collect_credentials"]
    assert body["collect_credentials"]["mysql"][0]["username"] == "u"


def test_trigger_database_not_selected_omits_mysql_collect_creds(mocker):
    sync_builtin_port_fingerprints()
    task = _scan_task(families=["host"], credentials={"host": []}, cloud_region={"id": 1})
    execution = ScanExecution.objects.create(task=task)
    scan, _admit = _patch_stargazer(mocker, scan_total=3)

    trigger_scan_execution(execution.id)

    body = scan.call_args.args[0]
    assert "mysql" not in (body.get("collect_credentials") or {})


def test_trigger_middleware_discover_once_includes_seven_types(mocker):
    sync_builtin_port_fingerprints()
    task = _scan_task(
        families=["middleware"],
        credentials={"middleware": [{"credential_id": "cred-ssh", "username": "root", "password": "p"}]},
        cloud_region={"id": 1},
    )
    execution = ScanExecution.objects.create(task=task)
    scan, admit = _patch_stargazer(mocker, scan_total=3)

    trigger_scan_execution(execution.id)

    scan.assert_called_once()
    admit.assert_not_called()
    body = scan.call_args.args[0]
    types = {item["target_type"] for item in body["port_fingerprints"]}
    assert SCAN_MIDDLEWARE_TYPES <= types
    for mw in SCAN_MIDDLEWARE_TYPES:
        assert mw in body["collect_credentials"]


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


def test_poll_completes_when_unique_hosts_received(mocker):
    task = _scan_task(families=["host"], credentials={"host": []}, cloud_region={"id": 1})
    execution = ScanExecution.objects.create(task=task)
    _patch_stargazer(mocker, scan_total=3)
    mocker.patch("apps.cmdb.services.scan_finalize_service.write_scan_execution", return_value={"status": "written"})
    trigger_scan_execution(execution.id)
    execution.refresh_from_db()
    execution.received_count = 3
    execution.save(update_fields=["received_count"])

    result = poll_scan_finalize(execution.id, execution.claim_token)

    assert result["status"] == ScanExecution.STATUS_COMPLETED


def test_recover_completes_when_celery_poll_chain_is_lost(mocker):
    from apps.cmdb.services.scan_trigger_service import recover_due_scan_execution

    task = _scan_task(families=["host"], credentials={"host": []}, cloud_region={"id": 1})
    execution = ScanExecution.objects.create(task=task)
    _patch_stargazer(mocker, scan_total=3)
    mocker.patch("apps.cmdb.services.scan_finalize_service.write_scan_execution", return_value={"status": "written"})
    trigger_scan_execution(execution.id)
    execution.refresh_from_db()
    execution.received_count = 3
    execution.save(update_fields=["received_count"])

    recovered = recover_due_scan_execution(execution)

    assert recovered.status == ScanExecution.STATUS_COMPLETED
    assert recovered.finished_at is not None


def test_recover_times_out_past_deadline_without_waiting_for_celery(mocker):
    from datetime import timedelta

    from django.utils.timezone import now

    from apps.cmdb.services.scan_trigger_service import recover_due_scan_execution

    task = _scan_task(families=["host"], credentials={"host": []}, cloud_region={"id": 1})
    execution = ScanExecution.objects.create(task=task)
    _patch_stargazer(mocker, scan_total=3)
    mocker.patch("apps.cmdb.services.scan_finalize_service.write_scan_execution", return_value={"status": "written"})
    trigger_scan_execution(execution.id)
    execution.refresh_from_db()
    execution.deadline_at = now() - timedelta(minutes=1)
    execution.save(update_fields=["deadline_at"])

    recovered = recover_due_scan_execution(execution)

    assert recovered.status == ScanExecution.STATUS_TIMED_OUT


def test_recover_leaves_in_progress_execution_alone(mocker):
    from apps.cmdb.services.scan_trigger_service import recover_due_scan_execution

    task = _scan_task(families=["host"], credentials={"host": []}, cloud_region={"id": 1})
    execution = ScanExecution.objects.create(task=task)
    _patch_stargazer(mocker, scan_total=3)
    trigger_scan_execution(execution.id)
    execution.refresh_from_db()

    recovered = recover_due_scan_execution(execution)

    assert recovered.status == ScanExecution.STATUS_RUNNING
    assert recovered.finished_at is None


def test_poll_waits_when_scan_in_progress(mocker):
    task = _scan_task(families=["host"], credentials={"host": []}, cloud_region={"id": 1})
    execution = ScanExecution.objects.create(task=task)
    _patch_stargazer(mocker, scan_total=3)
    trigger_scan_execution(execution.id)
    execution.refresh_from_db()

    result = poll_scan_finalize(execution.id, execution.claim_token)

    assert result["status"] == "waiting"
    execution.refresh_from_db()
    assert execution.status == ScanExecution.STATUS_RUNNING


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

    _patch_stargazer(mocker, scan_total=3, admit=fake_admit)
    trigger_scan_execution(execution.id)
    assert captured
    headers = captured[0]
    assert headers.get("cmdbcredential_0_version") == "v2"
    assert headers.get("cmdbcredential_1_version") == "v3"
