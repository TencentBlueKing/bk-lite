import time

import pytest

from apps.cmdb.constants.constants import DataCleanupStrategy
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


def _capture_cannula(mocker):
    captured = {}

    class FakeCannula:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self.collect_data = {}

        def collect_controller(self):
            metrics = captured.get("default_metrics") or {}
            result = {}
            for model_id, rows in metrics.items():
                success = []
                for row in rows or []:
                    success.append(
                        {
                            "inst_info": {
                                **row,
                                "inst_uuid": f"uuid-{row.get('ip_addr')}",
                                "model_id": model_id,
                            }
                        }
                    )
                result[model_id] = {
                    "add": {"success": success, "failed": []},
                    "update": {"success": [], "failed": []},
                    "delete": {"success": [], "failed": []},
                }
            result["__raw_data__"] = []
            result["all"] = sum(len(rows or []) for rows in metrics.values())
            return result

    mocker.patch("apps.cmdb.services.scan_finalize_service.MetricsCannula", FakeCannula)
    return captured


def test_unknown_soid_is_not_in_controller_metrics_and_hit_remains(mocker):
    execution, _family_run = _execution_with_network_hits(hosts=["10.0.1.11"])
    _patch_oid_map(mocker)
    now_ts = time.time()
    mocker.patch(
        "apps.cmdb.collection.collect_plugin.base.Collection.query",
        return_value={
            "data": {
                "result": [
                    {
                        "metric": {
                            "__name__": "network_system_info_gauge",
                            "sysobjectid": UNKNOWN_OID,
                            "host": "10.0.1.11",
                            "ip_addr": "10.0.1.11",
                            "collect_status": "success",
                        },
                        "value": [now_ts, "1"],
                    }
                ]
            }
        },
    )
    captured = _capture_cannula(mocker)

    write_scan_execution(execution)

    assert captured.get("default_metrics") in (None, {})
    hit = ScanHit.objects.get(host="10.0.1.11")
    assert hit.inst_uuid == ""
    assert hit.cmdb_model_id == ""
    assert ScanHit.objects.filter(pk=hit.pk).exists()


def test_known_switch_soid_goes_through_controller(mocker):
    execution, _family_run = _execution_with_network_hits(hosts=["10.0.1.10", "10.0.1.11"])
    _patch_oid_map(mocker)
    now_ts = time.time()
    mocker.patch(
        "apps.cmdb.collection.collect_plugin.base.Collection.query",
        return_value={
            "data": {
                "result": [
                    {
                        "metric": {
                            "__name__": "network_system_info_gauge",
                            "sysobjectid": KNOWN_SWITCH_OID,
                            "host": "10.0.1.10",
                            "ip_addr": "10.0.1.10",
                            "collect_status": "success",
                        },
                        "value": [now_ts, "1"],
                    },
                    {
                        "metric": {
                            "__name__": "network_system_info_gauge",
                            "sysobjectid": UNKNOWN_OID,
                            "host": "10.0.1.11",
                            "ip_addr": "10.0.1.11",
                            "collect_status": "success",
                        },
                        "value": [now_ts, "1"],
                    },
                ]
            }
        },
    )
    captured = _capture_cannula(mocker)

    write_scan_execution(execution)

    assert captured["filter_collect_task"] is False
    assert captured["data_cleanup_strategy"] == DataCleanupStrategy.NO_CLEANUP
    assert captured["manual"] is False
    switch_ips = [row.get("ip_addr") for row in (captured["default_metrics"] or {}).get("switch", [])]
    assert switch_ips == ["10.0.1.10"]
    known = ScanHit.objects.get(host="10.0.1.10")
    assert known.inst_uuid == "uuid-10.0.1.10"
    assert known.cmdb_model_id == "switch"
    assert known.soid == KNOWN_SWITCH_OID
    assert known.snapshot.get("sysobjectid") == KNOWN_SWITCH_OID or known.snapshot.get("soid") == KNOWN_SWITCH_OID
    unknown = ScanHit.objects.get(host="10.0.1.11")
    assert unknown.inst_uuid == ""
    assert unknown.cmdb_model_id == ""
    assert unknown.soid == UNKNOWN_OID
    assert unknown.snapshot.get("sysobjectid") == UNKNOWN_OID or unknown.snapshot.get("soid") == UNKNOWN_OID


def test_host_snapshot_backfills_os_facts(mocker):
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
        snapshot={"host": "10.0.1.20"},
    )
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        return_value={
            "host": [
                {
                    "ip_addr": "10.0.1.20",
                    "hostname": "web-1",
                    "os_type": "Linux",
                    "os_name": "Ubuntu",
                    "os_version": "22.04",
                }
            ]
        },
    )
    _capture_cannula(mocker)

    write_scan_execution(execution)

    hit = ScanHit.objects.get(host="10.0.1.20")
    assert hit.snapshot.get("hostname") == "web-1"
    assert hit.snapshot.get("os_type") == "Linux"
    assert hit.snapshot.get("os_name") == "Ubuntu"
    assert hit.cmdb_model_id == "host"
    assert hit.inst_uuid == "uuid-10.0.1.20"


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
        snapshot={"host": "10.0.1.20"},
    )
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        return_value={
            "host": [
                {
                    "ip_addr": "10.0.1.20",
                    "hostname": "web-1",
                    "os_type": "1",
                    "os_name": "CentOS Linux",
                    "os_version": "7",
                }
            ]
        },
    )
    _capture_cannula(mocker)

    write_scan_execution(execution)

    hit = ScanHit.objects.get(host="10.0.1.20")
    assert hit.snapshot.get("os_type") == "Linux"
    assert hit.snapshot.get("os_name") == "CentOS Linux"


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


def test_finalize_retries_when_host_row_has_ip_but_no_os_facts(mocker):
    task = _scan_task(families=["host"], credentials={"host": [{"username": "root", "port": "22"}]})
    execution = ScanExecution.objects.create(
        task=task,
        status=ScanExecution.STATUS_RUNNING,
        claim_token="token-ip-only",
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
        snapshot={"host": "10.0.1.20"},
    )
    calls = {"n": 0}

    def fake_collect(_family_run):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"host": [{"ip_addr": "10.0.1.20"}]}
        return {
            "host": [
                {
                    "ip_addr": "10.0.1.20",
                    "hostname": "web-1",
                    "os_name": "Ubuntu",
                    "os_type": "Linux",
                }
            ]
        }

    mocker.patch("apps.cmdb.services.scan_finalize_service.collect_family_metrics", side_effect=fake_collect)
    mocker.patch("apps.cmdb.services.scan_finalize_service.time.sleep")
    _capture_cannula(mocker)

    write_scan_execution(execution)

    hit = ScanHit.objects.get(host="10.0.1.20")
    assert calls["n"] == 2
    assert hit.snapshot.get("hostname") == "web-1"
    assert hit.snapshot.get("os_name") == "Ubuntu"


def test_finalize_retries_vm_until_success_hits_have_metrics(mocker):
    task = _scan_task(families=["host"], credentials={"host": [{"username": "root", "port": "22"}]})
    execution = ScanExecution.objects.create(
        task=task,
        status=ScanExecution.STATUS_RUNNING,
        claim_token="token-retry",
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
        snapshot={"host": "10.0.1.20"},
    )
    calls = {"n": 0}

    def fake_collect(_family_run):
        calls["n"] += 1
        if calls["n"] == 1:
            return {}
        return {
            "host": [
                {
                    "ip_addr": "10.0.1.20",
                    "hostname": "web-1",
                    "os_type": "Linux",
                    "os_name": "Ubuntu",
                    "os_version": "22.04",
                }
            ]
        }

    mocker.patch("apps.cmdb.services.scan_finalize_service.collect_family_metrics", side_effect=fake_collect)
    mocker.patch("apps.cmdb.services.scan_finalize_service.time.sleep")
    _capture_cannula(mocker)

    write_scan_execution(execution)

    hit = ScanHit.objects.get(host="10.0.1.20")
    assert calls["n"] == 2
    assert hit.snapshot.get("hostname") == "web-1"
    assert hit.snapshot.get("os_name") == "Ubuntu"


def test_snmp_without_network_ci_attaches_to_same_ip_ipmi(mocker):
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
    )
    mocker.patch(
        "apps.cmdb.services.scan_finalize_service.collect_family_metrics",
        side_effect=lambda family_run: (
            {"switch": [{"inst_name": "10.0.1.11-switch", "ip_addr": "10.0.1.11", "soid": UNKNOWN_OID}]}
            if family_run.model_id == "network"
            else {"physcial_server": [{"inst_name": "SN123", "ip_addr": "10.0.1.11", "serial_number": "SN123"}]}
        ),
    )
    _patch_oid_map(mocker)
    _capture_cannula(mocker)

    write_scan_execution(execution)

    snmp_hit = ScanHit.objects.get(family_run=network_run, host="10.0.1.11")
    physical_hit = ScanHit.objects.get(family_run=physical_run)
    assert physical_hit.inst_uuid == "uuid-10.0.1.11"
    assert physical_hit.snapshot.get("serial_number") == "SN123"
    assert snmp_hit.inst_uuid == ""
    assert snmp_hit.attached_inst_uuid == physical_hit.inst_uuid


def test_poll_ready_writes_ci_and_marks_completed(mocker):
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
