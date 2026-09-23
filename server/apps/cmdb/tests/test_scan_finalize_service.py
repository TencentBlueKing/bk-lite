import pytest

from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanHit, ScanTask
from apps.cmdb.services.scan_finalize_service import write_scan_execution
from apps.cmdb.services.scan_trigger_service import poll_scan_finalize

pytestmark = pytest.mark.django_db

KNOWN_SWITCH_OID = "1.3.6.1.4.1.9.1.1"
UNKNOWN_OID = "1.2.3.999"


def _scan_task(**overrides):
    values = {
        "name": "scan-finalize",
        "team": [1],
        "families": ["network"],
        "ip_ranges": [{"begin": "10.0.1.1", "end": "10.0.1.20"}],
        "access_point": [{"id": "node-1"}],
        "credentials": {"network": [{"version": "v2c", "community": "public"}]},
    }
    values.update(overrides)
    return ScanTask.objects.create(**values)


def _execution_with_network_hits(task=None, hosts=None):
    task = task or _scan_task()
    execution = ScanExecution.objects.create(
        task=task,
        status=ScanExecution.STATUS_RUNNING,
        claim_token="token-finalize",
        target_count=len(hosts or ["10.0.1.10"]),
        received_count=len(hosts or ["10.0.1.10"]),
    )
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="network",
        driver_type="protocol",
        target_count=execution.target_count,
        received_count=execution.received_count,
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    for host in hosts or ["10.0.1.10"]:
        ScanHit.objects.create(
            execution=execution,
            family_run=family_run,
            protocol="snmp",
            host=host,
            port=161,
            credential_id=f"cred-{host}",
            status=ScanHit.STATUS_SUCCESS,
            soid=KNOWN_SWITCH_OID if host.endswith(".10") else UNKNOWN_OID,
        )
    return execution, family_run


def _patch_oid_map(mocker):
    mocker.patch(
        "apps.cmdb.collection.collect_plugin.network.CollectNetworkMetrics.get_oid_map",
        staticmethod(
            lambda: {
                KNOWN_SWITCH_OID: {
                    "oid": KNOWN_SWITCH_OID,
                    "model": "Cisco",
                    "brand": "Cisco",
                    "device_type": "switch",
                    "built_in": True,
                }
            }
        ),
    )


def test_unknown_soid_stays_unclassified_and_is_not_written(mocker):
    execution, _family_run = _execution_with_network_hits(hosts=["10.0.1.11"])
    _patch_oid_map(mocker)
    cannula = mocker.patch("apps.cmdb.services.scan_finalize_service.MetricsCannula")
    collect = mocker.patch("apps.cmdb.services.scan_finalize_service.collect_family_metrics")

    write_scan_execution(execution)

    hit = ScanHit.objects.get(host="10.0.1.11")
    assert hit.inst_uuid == ""
    assert hit.cmdb_model_id == ""
    assert hit.snapshot.get("device_type") in (None, "")
    cannula.assert_not_called()
    collect.assert_not_called()


def test_known_switch_soid_annotates_snapshot_without_writing_ci(mocker):
    execution, _family_run = _execution_with_network_hits(hosts=["10.0.1.10", "10.0.1.11"])
    _patch_oid_map(mocker)
    cannula = mocker.patch("apps.cmdb.services.scan_finalize_service.MetricsCannula")

    write_scan_execution(execution)

    known = ScanHit.objects.get(host="10.0.1.10")
    assert known.inst_uuid == ""
    assert known.cmdb_model_id == ""
    assert known.soid == KNOWN_SWITCH_OID
    assert known.snapshot.get("device_type") == "switch"
    assert known.snapshot.get("brand") == "Cisco"
    unknown = ScanHit.objects.get(host="10.0.1.11")
    assert unknown.inst_uuid == ""
    assert unknown.cmdb_model_id == ""
    assert unknown.snapshot.get("device_type") in (None, "")
    cannula.assert_not_called()


def test_host_snapshot_from_nats_is_kept_without_writing_ci(mocker):
    task = _scan_task(families=["host"], credentials={"host": [{"username": "root", "port": "22"}]})
    execution = ScanExecution.objects.create(
        task=task,
        status=ScanExecution.STATUS_RUNNING,
        claim_token="token-host",
        target_count=1,
        received_count=1,
    )
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="host",
        driver_type="job",
        target_count=1,
        received_count=1,
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="host",
        host="10.0.1.20",
        port=22,
        credential_id="cred-host",
        status=ScanHit.STATUS_SUCCESS,
        snapshot={"host": "10.0.1.20", "hostname": "web-1", "os_type": "Linux", "os_name": "Ubuntu", "os_version": "22.04"},
    )
    cannula = mocker.patch("apps.cmdb.services.scan_finalize_service.MetricsCannula")
    collect = mocker.patch("apps.cmdb.services.scan_finalize_service.collect_family_metrics")

    write_scan_execution(execution)

    hit = ScanHit.objects.get(host="10.0.1.20")
    assert hit.snapshot.get("hostname") == "web-1"
    assert hit.snapshot.get("os_type") == "Linux"
    assert hit.snapshot.get("os_name") == "Ubuntu"
    assert hit.cmdb_model_id == ""
    assert hit.inst_uuid == ""
    cannula.assert_not_called()
    collect.assert_not_called()


def test_host_snapshot_maps_numeric_os_type_to_name(mocker):
    task = _scan_task(
        families=["host"],
        cloud_region=1,
        credentials={"host": [{"username": "root", "port": "22"}]},
    )
    execution = ScanExecution.objects.create(
        task=task,
        status=ScanExecution.STATUS_RUNNING,
        claim_token="token-os-type",
        target_count=1,
        received_count=1,
    )
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="host",
        driver_type="job",
        target_count=1,
        received_count=1,
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="host",
        host="10.0.1.20",
        port=22,
        credential_id="cred-host",
        status=ScanHit.STATUS_SUCCESS,
        snapshot={"host": "10.0.1.20", "os_type": "1", "os_name": "CentOS Linux"},
    )

    write_scan_execution(execution)

    hit = ScanHit.objects.get(host="10.0.1.20")
    assert hit.snapshot.get("os_type") == "Linux"
    assert hit.snapshot.get("os_name") == "CentOS Linux"
    assert hit.inst_uuid == ""


def test_host_shim_copies_scan_cloud_region():
    from apps.cmdb.services.scan_finalize_service import build_scan_collect_shim

    task = _scan_task(
        families=["host"],
        cloud_region=1,
        credentials={"host": [{"username": "root", "port": "22"}]},
    )
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_RUNNING)
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="host",
        driver_type="job",
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )

    shim = build_scan_collect_shim(family_run)

    assert shim.params.get("cloud") == 1
    assert shim.params.get("has_network_topo") is False


def test_finalize_does_not_attach_snmp_before_physical_ci(mocker):
    task = _scan_task(families=["network", "physcial_server"])
    execution, network_run = _execution_with_network_hits(task=task, hosts=["10.0.1.11"])
    physical_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="physcial_server",
        driver_type="protocol",
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    ScanHit.objects.create(
        execution=execution,
        family_run=physical_run,
        protocol="ipmi",
        host="10.0.1.11",
        port=623,
        credential_id="cred-ipmi",
        status=ScanHit.STATUS_SUCCESS,
        snapshot={"serial_number": "SN123", "ip_addr": "10.0.1.11"},
    )
    _patch_oid_map(mocker)

    write_scan_execution(execution)

    snmp_hit = ScanHit.objects.get(family_run=network_run, host="10.0.1.11")
    physical_hit = ScanHit.objects.get(family_run=physical_run)
    assert physical_hit.inst_uuid == ""
    assert physical_hit.snapshot.get("serial_number") == "SN123"
    assert snmp_hit.inst_uuid == ""
    assert snmp_hit.attached_inst_uuid == ""


def test_finalize_explodes_middleware_listen_ports_and_keeps_empty_host(mocker):
    from apps.cmdb.constants.constants import CollectDriverTypes

    task = _scan_task(families=["middleware"], credentials={"middleware": [{"credential_id": "cred-ssh"}]})
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_RUNNING, claim_token="t")
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="nginx",
        driver_type=CollectDriverTypes.JOB,
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="nginx",
        host="10.0.1.10",
        port=22,
        credential_id="cred-ssh",
        status=ScanHit.STATUS_SUCCESS,
    )
    ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="nginx",
        host="10.0.1.11",
        port=22,
        credential_id="cred-ssh",
        status=ScanHit.STATUS_SUCCESS,
    )
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        return_value={
            "nginx": [
                {
                    "ip_addr": "10.0.1.10",
                    "listen_port": "80",
                    "version": "1.24",
                    "conf_path": "/etc/nginx/nginx.conf",
                    "inst_name": "10.0.1.10-nginx-80",
                }
            ]
        },
    )
    mocker.patch("apps.cmdb.services.scan_finalize_service.schedule_middleware_snapshot_enrich", return_value=True)
    write_scan_execution(execution)
    ports = set(ScanHit.objects.filter(family_run=family_run, status=ScanHit.STATUS_SUCCESS).values_list("host", "port"))
    assert ports == {("10.0.1.10", 80), ("10.0.1.11", 80)}
    hit = ScanHit.objects.get(host="10.0.1.10", port=80)
    assert hit.snapshot.get("version") == "1.24"
    assert hit.cmdb_model_id == "nginx"
    kept = ScanHit.objects.get(host="10.0.1.11", port=80)
    assert kept.cmdb_model_id == "nginx"
    assert not ScanHit.objects.filter(host="10.0.1.11", port=22).exists()


def test_finalize_creates_middleware_hits_from_metrics_without_ssh_template(mocker):
    from apps.cmdb.constants.constants import CollectDriverTypes

    task = _scan_task(families=["middleware"], credentials={"middleware": [{"credential_id": "cred-ssh"}]})
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_RUNNING, claim_token="t")
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="nginx",
        driver_type=CollectDriverTypes.JOB,
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        return_value={
            "nginx": [
                {
                    "ip_addr": "10.11.27.147",
                    "listen_port": "80",
                    "version": "1.20.1",
                    "inst_name": "10.11.27.147-nginx-80",
                }
            ]
        },
    )
    mocker.patch("apps.cmdb.services.scan_finalize_service.schedule_middleware_snapshot_enrich", return_value=True)
    write_scan_execution(execution)
    hit = ScanHit.objects.get(family_run=family_run, host="10.11.27.147", port=80)
    assert hit.status == ScanHit.STATUS_SUCCESS
    assert hit.cmdb_model_id == "nginx"
    assert hit.snapshot.get("version") == "1.20.1"


def _nginx_job_execution():
    from apps.cmdb.constants.constants import CollectDriverTypes

    task = _scan_task(families=["middleware"], credentials={"middleware": [{"credential_id": "cred-ssh"}]})
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_RUNNING, claim_token="t")
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="nginx",
        driver_type=CollectDriverTypes.JOB,
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="nginx",
        host="10.0.1.10",
        port=22,
        credential_id="cred-ssh",
        status=ScanHit.STATUS_SUCCESS,
        snapshot={"password": "secret-password"},
    )
    return execution, family_run


def test_finalize_keeps_identity_and_schedules_path_enrich(mocker, caplog):
    import logging

    from apps.cmdb.services.scan_finalize_service import SCAN_MIDDLEWARE_ENRICH_DEADLINE_SECONDS

    execution, family_run = _nginx_job_execution()
    identity_only = {
        "ip_addr": "10.0.1.10",
        "listen_port": "80",
        "version": "1.20.1",
        "inst_name": "10.0.1.10-nginx-80",
    }
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        return_value={"nginx": [identity_only]},
    )
    slept = mocker.patch("apps.cmdb.services.scan_finalize_service.time.sleep")
    now_ts = 1_700_000_000
    mocker.patch("apps.cmdb.services.scan_finalize_service.time.time", return_value=now_ts)
    apply_async = mocker.patch("apps.cmdb.tasks.celery_tasks.enrich_scan_middleware_snapshots.apply_async")
    with caplog.at_level(logging.INFO, logger="cmdb"):
        write_scan_execution(execution)
    slept.assert_not_called()
    apply_async.assert_called_once_with(
        args=(execution.id, 0, now_ts + SCAN_MIDDLEWARE_ENRICH_DEADLINE_SECONDS),
        countdown=15,
    )
    hit = ScanHit.objects.get(family_run=family_run, status=ScanHit.STATUS_SUCCESS)
    assert (hit.host, hit.port) == ("10.0.1.10", 80)
    assert hit.snapshot.get("version") == "1.20.1"
    assert not hit.snapshot.get("conf_path")
    records = [record for record in caplog.records if record.msg == "[ScanFinalize] 中间件路径待补齐 execution=%s"]
    assert len(records) == 1
    assert records[0].args == (execution.id,)
    assert records[0].getMessage() == f"[ScanFinalize] 中间件路径待补齐 execution={execution.id}"
    assert "secret-password" not in caplog.text


def test_finalize_does_not_schedule_enrich_when_paths_ready(mocker):
    execution, family_run = _nginx_job_execution()
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        return_value={
            "nginx": [
                {
                    "ip_addr": "10.0.1.10",
                    "listen_port": "80",
                    "version": "1.20.1",
                    "inst_name": "10.0.1.10-nginx-80",
                    "conf_path": "/etc/nginx/nginx.conf",
                    "bin_path": "/usr/sbin/nginx",
                }
            ]
        },
    )
    apply_async = mocker.patch("apps.cmdb.tasks.celery_tasks.enrich_scan_middleware_snapshots.apply_async")
    write_scan_execution(execution)
    apply_async.assert_not_called()
    hit = ScanHit.objects.get(family_run=family_run, status=ScanHit.STATUS_SUCCESS)
    assert hit.snapshot.get("conf_path") == "/etc/nginx/nginx.conf"


def test_enrich_fills_middleware_paths_after_finalize(mocker, caplog):
    import logging

    from apps.cmdb.services.scan_finalize_service import enrich_middleware_snapshots

    execution, family_run = _nginx_job_execution()
    identity_only = {
        "ip_addr": "10.0.1.10",
        "listen_port": "80",
        "version": "1.20.1",
        "inst_name": "10.0.1.10-nginx-80",
    }
    with_paths = {
        **identity_only,
        "conf_path": "/etc/nginx/nginx.conf",
        "bin_path": "/usr/sbin/nginx",
        "log_path": "/var/log/nginx/error.log",
    }
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        return_value={"nginx": [identity_only]},
    )
    mocker.patch("apps.cmdb.tasks.celery_tasks.enrich_scan_middleware_snapshots.apply_async")
    write_scan_execution(execution)
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        return_value={"nginx": [with_paths]},
    )
    apply_async = mocker.patch("apps.cmdb.tasks.celery_tasks.enrich_scan_middleware_snapshots.apply_async")
    with caplog.at_level(logging.INFO, logger="cmdb"):
        result = enrich_middleware_snapshots(execution.id, attempt=0, deadline_ts=1_700_003_600)
    assert result == {"status": "ready", "execution_id": execution.id}
    apply_async.assert_not_called()
    hit = ScanHit.objects.get(family_run=family_run, status=ScanHit.STATUS_SUCCESS)
    assert hit.port == 80
    assert hit.snapshot.get("conf_path") == "/etc/nginx/nginx.conf"
    assert hit.snapshot.get("bin_path") == "/usr/sbin/nginx"
    records = [record for record in caplog.records if record.msg == "[ScanFinalize] 中间件路径已补齐 execution=%s"]
    assert len(records) == 1
    assert records[0].args == (execution.id,)
    assert records[0].getMessage() == f"[ScanFinalize] 中间件路径已补齐 execution={execution.id}"
    assert "secret-password" not in caplog.text


def test_enrich_reschedules_when_paths_still_missing(mocker):
    from apps.cmdb.services.scan_finalize_service import enrich_middleware_snapshots

    execution, _family_run = _nginx_job_execution()
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        return_value={
            "nginx": [
                {
                    "ip_addr": "10.0.1.10",
                    "listen_port": "80",
                    "version": "1.20.1",
                    "inst_name": "10.0.1.10-nginx-80",
                }
            ]
        },
    )
    now_ts = 1_700_000_000
    mocker.patch("apps.cmdb.services.scan_finalize_service.time.time", return_value=now_ts)
    apply_async = mocker.patch("apps.cmdb.tasks.celery_tasks.enrich_scan_middleware_snapshots.apply_async")
    result = enrich_middleware_snapshots(execution.id, attempt=2, deadline_ts=now_ts + 3600)
    assert result == {"status": "scheduled", "execution_id": execution.id, "attempt": 3}
    apply_async.assert_called_once_with(args=(execution.id, 3, now_ts + 3600), countdown=120)


def test_enrich_stops_after_deadline(mocker, caplog):
    import logging

    from apps.cmdb.services.scan_finalize_service import enrich_middleware_snapshots

    execution, family_run = _nginx_job_execution()
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        return_value={
            "nginx": [
                {
                    "ip_addr": "10.0.1.10",
                    "listen_port": "80",
                    "version": "1.20.1",
                    "inst_name": "10.0.1.10-nginx-80",
                }
            ]
        },
    )
    now_ts = 1_700_003_600
    mocker.patch("apps.cmdb.services.scan_finalize_service.time.time", return_value=now_ts)
    apply_async = mocker.patch("apps.cmdb.tasks.celery_tasks.enrich_scan_middleware_snapshots.apply_async")
    with caplog.at_level(logging.WARNING, logger="cmdb"):
        result = enrich_middleware_snapshots(execution.id, attempt=5, deadline_ts=now_ts - 1)
    assert result == {"status": "stopped", "execution_id": execution.id}
    apply_async.assert_not_called()
    hit = ScanHit.objects.get(family_run=family_run, status=ScanHit.STATUS_SUCCESS)
    assert hit.snapshot.get("version") == "1.20.1"
    assert not hit.snapshot.get("conf_path")
    records = [record for record in caplog.records if record.msg == "[ScanFinalize] 中间件路径补齐停止 execution=%s attempt=%s"]
    assert len(records) == 1
    assert records[0].args == (execution.id, 5)
    assert records[0].getMessage() == f"[ScanFinalize] 中间件路径补齐停止 execution={execution.id} attempt=5"
    assert "secret-password" not in caplog.text


def test_poll_ready_finalizes_and_marks_completed(mocker):
    execution, _family_run = _execution_with_network_hits()
    write = mocker.patch(
        "apps.cmdb.services.scan_finalize_service.write_scan_execution",
        return_value={"status": "written"},
    )
    result = poll_scan_finalize(execution.id, execution.claim_token)
    assert result["status"] == ScanExecution.STATUS_COMPLETED
    write.assert_called_once()
    execution.refresh_from_db()
    assert execution.status == ScanExecution.STATUS_COMPLETED
    assert execution.finished_at is not None
