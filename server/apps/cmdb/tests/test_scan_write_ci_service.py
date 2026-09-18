import pytest

from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanHit, ScanTask
from apps.cmdb.services.scan_write_ci_service import ScanWriteCiService
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.django_db


def _task(**overrides):
    values = {
        "name": "scan-write-ci",
        "team": [1],
        "families": ["network"],
        "access_point": [{"id": "node-1"}],
        "credentials": {"network": [{"credential_id": "cred-1", "version": "v2c", "community": "public"}]},
    }
    values.update(overrides)
    return ScanTask.objects.create(**values)


def _execution(
    *, family="network", status=ScanExecution.STATUS_COMPLETED, hit_status=ScanHit.STATUS_SUCCESS, driver_type="protocol", **hit_overrides
):
    task = _task(families=[family] if family != "network" else ["network"])
    execution = ScanExecution.objects.create(task=task, status=status)
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id=family,
        driver_type=driver_type,
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    values = {
        "execution": execution,
        "family_run": family_run,
        "protocol": family,
        "host": "10.0.1.10",
        "port": 161,
        "credential_id": "cred-1",
        "status": hit_status,
        "soid": "1.3.6.1.4.1.9.1.1",
        "snapshot": {"device_type": "switch", "brand": "Cisco", "sysname": "sw-1", "ip_addr": "10.0.1.10"},
    }
    values.update(hit_overrides)
    hit = ScanHit.objects.create(**values)
    return execution, hit


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


def _patch_host_graph_lookup(mocker, rows):
    fake_graph = mocker.MagicMock()
    fake_graph.query_entity.return_value = (rows, len(rows))
    mocker.patch(
        "apps.cmdb.graph.drivers.graph_client.GraphClient",
        return_value=mocker.MagicMock(__enter__=mocker.Mock(return_value=fake_graph), __exit__=mocker.Mock(return_value=False)),
    )
    return fake_graph


def test_write_ci_from_snapshot_backfills_uuid(mocker):
    execution, hit = _execution()
    captured = _capture_cannula(mocker)

    result = ScanWriteCiService.write(execution, [hit.id])

    assert result["written"] == 1
    assert result["failed"] == 0
    hit.refresh_from_db()
    assert hit.inst_uuid == "uuid-10.0.1.10"
    assert hit.cmdb_model_id == "switch"
    assert captured["default_metrics"]["switch"][0]["ip_addr"] == "10.0.1.10"
    assert captured["default_metrics"]["switch"][0]["brand"] == "Cisco"


_EXISTING_SWITCH_UUID = "8e8375d9-ffe6-4f9a-be33-3ac3d288a75d"


def test_write_ci_skips_already_written(mocker):
    execution, hit = _execution(inst_uuid=_EXISTING_SWITCH_UUID, cmdb_model_id="switch")
    mocker.patch(
        "apps.cmdb.services.instance.InstanceManage.query_entity_by_uuids",
        return_value=[{"inst_uuid": _EXISTING_SWITCH_UUID, "model_id": "switch", "ip_addr": "10.0.1.10"}],
    )
    cannula = mocker.patch("apps.cmdb.services.scan_finalize_service.MetricsCannula")

    result = ScanWriteCiService.write(execution, [hit.id])

    assert result["written"] == 0
    assert result["skipped"] == 1
    assert result["items"][0]["status"] == "already_written"
    cannula.assert_not_called()


def test_write_ci_rewrites_when_recorded_uuid_missing_in_graph(mocker):
    execution, hit = _execution(inst_uuid=_EXISTING_SWITCH_UUID, cmdb_model_id="switch")
    mocker.patch("apps.cmdb.services.instance.InstanceManage.query_entity_by_uuids", return_value=[])
    captured = _capture_cannula(mocker)

    result = ScanWriteCiService.write(execution, [hit.id])

    assert result["written"] == 1
    assert result["skipped"] == 0
    assert result["items"][0]["status"] == "written"
    hit.refresh_from_db()
    assert hit.inst_uuid == "uuid-10.0.1.10"
    assert captured["default_metrics"]["switch"][0]["ip_addr"] == "10.0.1.10"


def test_write_ci_rejects_unclassified_network(mocker):
    execution, hit = _execution(soid="1.2.3.999", snapshot={"sysname": "unknown"})
    cannula = mocker.patch("apps.cmdb.services.scan_finalize_service.MetricsCannula")

    result = ScanWriteCiService.write(execution, [hit.id])

    assert result["written"] == 0
    assert result["items"][0]["reason"] == "need_classify"
    hit.refresh_from_db()
    assert hit.inst_uuid == ""
    cannula.assert_not_called()


def test_write_ci_rejects_credential_failed(mocker):
    execution, hit = _execution(
        family="postgresql",
        protocol="postgresql",
        port=5432,
        credential_id="",
        hit_status=ScanHit.STATUS_FAILED,
        soid="",
        snapshot={"ip_addr": "10.0.1.10", "port": 5432},
    )
    cannula = mocker.patch("apps.cmdb.services.scan_finalize_service.MetricsCannula")

    result = ScanWriteCiService.write(execution, [hit.id])

    assert result["items"][0]["reason"] == "credential_failed"
    cannula.assert_not_called()


def test_write_ci_rejects_running_execution():
    execution, hit = _execution(status=ScanExecution.STATUS_RUNNING)
    with pytest.raises(BaseAppException, match="尚未收口"):
        ScanWriteCiService.write(execution, [hit.id])


def test_write_postgresql_from_snapshot(mocker):
    execution, hit = _execution(
        family="postgresql",
        protocol="postgresql",
        port=5432,
        soid="",
        snapshot={"ip_addr": "10.0.1.10", "port": 5432, "version": "16"},
    )
    captured = _capture_cannula(mocker)

    result = ScanWriteCiService.write(execution, [hit.id])

    assert result["written"] == 1
    hit.refresh_from_db()
    assert hit.inst_uuid == "uuid-10.0.1.10"
    assert hit.cmdb_model_id == "postgresql"
    row = captured["default_metrics"]["postgresql"][0]
    assert row["inst_name"] == "10.0.1.10-pg-5432"
    assert row["port"] == 5432


def test_write_host_copies_scan_cloud_region(mocker):
    execution, hit = _execution(
        family="host",
        protocol="host",
        port=22,
        soid="",
        snapshot={"ip_addr": "10.0.1.10", "hostname": "box-1", "os_type": "Linux"},
    )
    execution.task.cloud_region = {"id": 7, "name": "gz"}
    execution.task.save(update_fields=["cloud_region"])
    captured = _capture_cannula(mocker)

    result = ScanWriteCiService.write(execution, [hit.id])

    assert result["written"] == 1
    row = captured["default_metrics"]["host"][0]
    assert row["inst_name"] == "box-1"
    assert row["cloud"] == 7
    assert row["cloud_name"] == "gz"


def _nginx_execution(**hit_overrides):
    snapshot = {
        "inst_name": "10.0.1.10-nginx-80",
        "ip_addr": "10.0.1.10",
        "listen_port": "80",
        "version": "1.24",
        "conf_path": "/etc/nginx/nginx.conf",
    }
    snapshot.update(hit_overrides.pop("snapshot", {}))
    return _execution(
        family="nginx",
        driver_type="job",
        port=80,
        snapshot=snapshot,
        cmdb_model_id="",
        soid="",
        **hit_overrides,
    )


def test_write_ci_maps_nginx_snapshot(mocker):
    execution, hit = _nginx_execution(snapshot={"catalina_path": "/usr/share/tomcat9"})
    captured = _capture_cannula(mocker)
    _patch_host_graph_lookup(mocker, [])
    mocker.patch("apps.cmdb.services.instance.InstanceManage.instance_association_create_by_uuid")
    result = ScanWriteCiService.write(execution, [hit.id])
    assert result["written"] == 1
    row = captured["default_metrics"]["nginx"][0]
    assert row["port"] == 80
    assert row["version"] == "1.24"
    assert row["conf_path"] == "/etc/nginx/nginx.conf"
    assert row["catalina_path"] == "/usr/share/tomcat9"
    assert row["assos"] == [
        {
            "model_id": "host",
            "inst_name": "10.0.1.10",
            "asst_id": "run",
            "model_asst_id": "nginx_run_host",
        }
    ]
    hit.refresh_from_db()
    assert hit.cmdb_model_id == "nginx"


_HOST_UUID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeffff0001"


def test_write_ci_attaches_middleware_to_existing_host(mocker):
    execution, hit = _nginx_execution()
    _capture_cannula(mocker)
    fake_graph = _patch_host_graph_lookup(
        mocker,
        [{"_id": 11, "inst_uuid": _HOST_UUID, "ip_addr": "10.0.1.10", "inst_name": "box-1", "model_id": "host"}],
    )
    create_asso = mocker.patch("apps.cmdb.services.instance.InstanceManage.instance_association_create_by_uuid")

    result = ScanWriteCiService.write(execution, [hit.id])

    assert result["written"] == 1
    hit.refresh_from_db()
    assert hit.attached_inst_uuid == _HOST_UUID
    create_asso.assert_called_once_with(
        src_inst_uuid="uuid-10.0.1.10",
        dst_inst_uuid=_HOST_UUID,
        model_asst_id="nginx_run_host",
        operator="scan",
    )
    _label, filters = fake_graph.query_entity.call_args[0]
    assert filters == [
        {"field": "model_id", "type": "str=", "value": "host"},
        {"field": "ip_addr", "type": "str=", "value": "10.0.1.10"},
    ]


def test_write_ci_skips_middleware_host_attach_when_host_missing(mocker):
    execution, hit = _nginx_execution()
    captured = _capture_cannula(mocker)
    _patch_host_graph_lookup(mocker, [])
    create_asso = mocker.patch("apps.cmdb.services.instance.InstanceManage.instance_association_create_by_uuid")

    result = ScanWriteCiService.write(execution, [hit.id])

    assert result["written"] == 1
    assert "host" not in captured["default_metrics"]
    hit.refresh_from_db()
    assert hit.attached_inst_uuid == ""
    create_asso.assert_not_called()


def test_write_ci_skips_middleware_host_attach_when_graph_lookup_fails(mocker):
    execution, hit = _nginx_execution()
    _capture_cannula(mocker)
    fake_graph = mocker.MagicMock()
    fake_graph.query_entity.side_effect = RuntimeError("graph down")
    mocker.patch(
        "apps.cmdb.graph.drivers.graph_client.GraphClient",
        return_value=mocker.MagicMock(__enter__=mocker.Mock(return_value=fake_graph), __exit__=mocker.Mock(return_value=False)),
    )
    create_asso = mocker.patch("apps.cmdb.services.instance.InstanceManage.instance_association_create_by_uuid")

    result = ScanWriteCiService.write(execution, [hit.id])

    assert result["written"] == 1
    hit.refresh_from_db()
    assert hit.attached_inst_uuid == ""
    create_asso.assert_not_called()
