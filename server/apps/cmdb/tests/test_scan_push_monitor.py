import pytest

from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanHit, ScanTask
from apps.cmdb.services.scan_push_monitor import ScanPushMonitorService

pytestmark = pytest.mark.django_db

UUID_SWITCH = "a1b2c3d4-e5f6-4a70-8b9c-0d1e2f3a4b5c"
UUID_SWITCH_LIVE = "b2c3d4e5-f6a7-4b81-9c0d-1e2f3a4b5c6d"
UUID_INFLUX = "c3d4e5f6-a7b8-4c92-8d1e-2f3a4b5c6d7e"


def _scan_with_hits(**task_overrides):
    values = {
        "name": "scan-push",
        "team": [1],
        "families": ["network"],
        "access_point": [{"id": "node-1"}],
        "credentials": {
            "network": [
                {
                    "credential_id": "cred-snmp-1",
                    "version": "v2",
                    "community": "public",
                    "snmp_port": "161",
                    "_client_id": "client-snmp-1",
                }
            ]
        },
    }
    values.update(task_overrides)
    task = ScanTask.objects.create(**values)
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_COMPLETED)
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="network",
        driver_type="protocol",
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    known = ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="network",
        host="10.0.1.10",
        port=161,
        credential_id="cred-snmp-1",
        status=ScanHit.STATUS_SUCCESS,
        cmdb_model_id="switch",
        inst_uuid=UUID_SWITCH,
    )
    unknown = ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="network",
        host="10.0.1.11",
        port=161,
        credential_id="cred-snmp-1",
        status=ScanHit.STATUS_SUCCESS,
        cmdb_model_id="",
        inst_uuid="",
    )
    return execution, known, unknown


def _patch_monitor_ingest(mocker, return_value=None, side_effect=None):
    """扫描经 CmdbToMonitorPush → Monitor.ingest_from_source，不直连监控内部。"""
    ingest = mocker.patch("apps.cmdb.services.module_push.Monitor").return_value.ingest_from_source
    if side_effect is not None:
        ingest.side_effect = side_effect
    else:
        ingest.return_value = return_value or {"id": "m1", "created": True}
    return ingest


def test_unknown_soid_does_not_call_ingest(mocker):
    execution, known, unknown = _scan_with_hits()
    ingest = _patch_monitor_ingest(mocker, return_value={"id": "m1", "created": True})
    mocker.patch(
        "apps.cmdb.services.scan_push_monitor.InstanceManage.query_entity_by_uuids",
        return_value=[
            {
                "_id": 101,
                "inst_uuid": UUID_SWITCH,
                "ip_addr": "10.0.1.10",
                "model_id": "switch",
            }
        ],
    )
    backfill = mocker.patch(
        "apps.cmdb.services.module_push.CmdbToMonitorPushService._backfill_monitor_id",
        return_value={},
    )

    result = ScanPushMonitorService.push(execution, [known.id, unknown.id], operator="alice")

    assert result["pushed"] == 1
    assert result["skipped"] == 1
    skipped = next(item for item in result["items"] if item["hit_id"] == unknown.id)
    assert skipped["reason"] == "no_ci"
    ingest.assert_called_once()
    payload = ingest.call_args.kwargs
    assert payload["allow_credential_create"] is True
    assert payload["raw"]["credential"]["community"] == "public"
    assert "_client_id" not in payload["raw"]["credential"]
    assert "credential" not in (payload.get("link_ids") or {})
    backfill.assert_called_once()
    assert backfill.call_args.args[1] == "m1"


def test_missing_graph_ci_does_not_call_ingest(mocker):
    execution, known, _unknown = _scan_with_hits()
    ingest = _patch_monitor_ingest(mocker)
    mocker.patch(
        "apps.cmdb.services.scan_push_monitor.InstanceManage.query_entity_by_uuids",
        return_value=[],
    )
    mocker.patch("apps.cmdb.services.scan_push_monitor._lookup_instance_by_ip", return_value=None)

    result = ScanPushMonitorService.push(execution, [known.id], operator="alice")

    assert result["pushed"] == 0
    assert result["failed"] == 1
    assert result["items"][0]["reason"] == "ci_not_found"
    ingest.assert_not_called()


def test_stale_hit_uuid_falls_back_to_ip_model(mocker):
    execution, known, _unknown = _scan_with_hits()
    ingest = _patch_monitor_ingest(mocker, return_value={"id": "m-live", "created": True})
    mocker.patch(
        "apps.cmdb.services.scan_push_monitor.InstanceManage.query_entity_by_uuids",
        return_value=[],
    )
    mocker.patch(
        "apps.cmdb.services.scan_push_monitor._lookup_instance_by_ip",
        return_value={
            "_id": 406,
            "inst_uuid": UUID_SWITCH_LIVE,
            "ip_addr": "10.0.1.10",
            "model_id": "switch",
            "organization": [1],
        },
    )
    backfill = mocker.patch(
        "apps.cmdb.services.module_push.CmdbToMonitorPushService._backfill_monitor_id",
        return_value={},
    )

    result = ScanPushMonitorService.push(execution, [known.id], operator="alice")

    assert result["pushed"] == 1
    ingest.assert_called_once()
    payload = ingest.call_args.kwargs
    assert payload["link_ids"]["cmdb_id"] == UUID_SWITCH_LIVE
    assert payload["raw"]["ip_addr"] == "10.0.1.10"
    backfill.assert_called_once()
    known.refresh_from_db()
    assert known.inst_uuid == UUID_SWITCH_LIVE


def test_influx_token_credential_is_passed_to_ingest(mocker):
    task = ScanTask.objects.create(
        name="scan-influx",
        team=[1],
        families=["influxdb"],
        access_point=[{"id": "node-1"}],
        cloud_region={"id": 3, "name": "region-3"},
        credentials={
            "influxdb": [
                {
                    "credential_id": "cred-inf-1",
                    "scheme": "https",
                    "port": 8086,
                    "token": "op-token",
                    "_client_id": "client-inf-1",
                }
            ]
        },
    )
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_COMPLETED)
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="influxdb",
        driver_type="protocol",
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    hit = ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="influxdb",
        host="10.0.1.60",
        port=8086,
        credential_id="cred-inf-1",
        status=ScanHit.STATUS_SUCCESS,
        cmdb_model_id="influxdb",
        inst_uuid=UUID_INFLUX,
    )
    ingest = _patch_monitor_ingest(mocker, return_value={"id": "inf-m1", "created": True})
    mocker.patch(
        "apps.cmdb.services.scan_push_monitor.InstanceManage.query_entity_by_uuids",
        return_value=[
            {
                "_id": 202,
                "inst_uuid": UUID_INFLUX,
                "ip_addr": "10.0.1.60",
                "model_id": "influxdb",
            }
        ],
    )
    mocker.patch(
        "apps.cmdb.services.module_push.CmdbToMonitorPushService._backfill_monitor_id",
        return_value={},
    )

    result = ScanPushMonitorService.push(execution, [hit.id], operator="alice")

    assert result["pushed"] == 1
    payload = ingest.call_args.kwargs
    credential = payload["raw"]["credential"]
    assert credential["token"] == "op-token"
    assert credential["scheme"] == "https"
    assert "_client_id" not in credential
    assert payload["raw"]["model_id"] == "influxdb"
    assert payload["raw"]["cloud_region_id"] == 3
    assert payload["raw"]["port"] == 8086


def test_empty_hit_uuid_is_rejected_without_ip_fallback(mocker):
    """无 inst_uuid 时不得按 IP 代查出 CI 再推送。"""
    task = ScanTask.objects.create(
        name="scan-host",
        team=[1],
        families=["host"],
        access_point=[{"id": "node-1"}],
        credentials={
            "host": [
                {
                    "credential_id": "cred-host-1",
                    "username": "root",
                    "password": "secret",
                    "port": 22,
                    "_client_id": "client-host-1",
                }
            ]
        },
    )
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_COMPLETED)
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="host",
        driver_type="protocol",
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    hit = ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="host",
        host="10.0.1.20",
        port=22,
        credential_id="cred-host-1",
        status=ScanHit.STATUS_SUCCESS,
        cmdb_model_id="host",
        inst_uuid="",
    )
    live_uuid = "d4e5f6a7-b8c9-4d03-9e2f-3a4b5c6d7e8f"
    ingest = _patch_monitor_ingest(mocker, return_value={"id": "host-m1", "created": True})
    mocker.patch(
        "apps.cmdb.services.scan_push_monitor._lookup_instance_by_ip",
        return_value={
            "_id": 501,
            "inst_uuid": live_uuid,
            "ip_addr": "10.0.1.20",
            "model_id": "host",
            "organization": [1],
        },
    )
    mocker.patch(
        "apps.cmdb.services.module_push.CmdbToMonitorPushService._backfill_monitor_id",
        return_value={},
    )

    result = ScanPushMonitorService.push(execution, [hit.id], operator="alice")

    assert result["pushed"] == 0
    assert result["skipped"] == 1
    assert result["items"][0]["reason"] == "no_ci"
    ingest.assert_not_called()
    hit.refresh_from_db()
    assert hit.inst_uuid == ""


def test_push_binds_monitor_native_id_and_cmdb_id(mocker):
    """推送后：监控主键走接入页 identity adapter；监控写 cmdb_id；CMDB 回写 monitor_id。"""
    from apps.monitor.models import MonitorInstance, MonitorObject, MonitorPlugin, MonitorPluginConfigTemplate
    from apps.monitor.services.module_ingest import MonitorModuleIngestService
    from apps.monitor.services.node_mgmt import InstanceConfigService
    from apps.monitor.utils.dimension import build_safe_instance_id, normalize_instance_identity

    switch_object = MonitorObject.objects.create(name="Switch", display_name="交换机", level="base")
    plugin = MonitorPlugin.objects.create(
        name="Switch SNMP General",
        collector="Telegraf",
        collect_type="snmp",
    )
    plugin.monitor_object.add(switch_object)
    MonitorPluginConfigTemplate.objects.create(
        plugin=plugin,
        type="switch",
        config_type="child",
        file_type="toml",
        content="# test",
    )

    inst_uuid = "10fc3cf6-064d-4e76-bc75-e7f23fa4f13a"
    storage_key = normalize_instance_identity(build_safe_instance_id(1, "10.0.1.10"))["storage_instance_key"]
    execution, known, _unknown = _scan_with_hits()
    known.inst_uuid = inst_uuid
    known.save(update_fields=["inst_uuid"])

    mocker.patch(
        "apps.cmdb.services.scan_push_monitor.InstanceManage.query_entity_by_uuids",
        return_value=[
            {
                "_id": 101,
                "inst_uuid": inst_uuid,
                "ip_addr": "10.0.1.10",
                "model_id": "switch",
                "organization": [1],
            }
        ],
    )
    # IoC：Monitor.ingest_from_source → 本进程落到 MonitorModuleIngestService.ingest
    mocker.patch(
        "apps.cmdb.services.module_push.Monitor"
    ).return_value.ingest_from_source.side_effect = lambda **kwargs: MonitorModuleIngestService.ingest(kwargs)

    node_mgmt = mocker.patch("apps.monitor.services.module_ingest.NodeMgmt")
    node_mgmt.return_value.node_list.return_value = {
        "count": 1,
        "nodes": [{"id": "container-1", "cloud_region_id": 1}],
    }

    def _fake_onboarding(payload, actor_context=None):
        prepared = InstanceConfigService._prepare_network_device_identity_instances(payload["instances"])
        MonitorInstance.objects.create(
            id=prepared[0]["storage_instance_key"],
            name=payload["instances"][0]["instance_name"],
            monitor_object_id=payload["monitor_object_id"],
        )

    mocker.patch(
        "apps.monitor.services.node_mgmt.InstanceConfigService.create_monitor_instance_by_node_mgmt",
        side_effect=_fake_onboarding,
    )
    mocker.patch(
        "apps.monitor.services.module_ingest.MonitorModuleIngestService._best_effort_notify_peers_on_create",
        return_value=None,
    )
    backfill = mocker.patch(
        "apps.cmdb.services.module_push.CmdbToMonitorPushService._backfill_monitor_id",
        return_value={},
    )

    result = ScanPushMonitorService.push(execution, [known.id], operator="alice")

    assert result["pushed"] == 1
    monitor_id = result["items"][0]["monitor_result"]["id"]
    assert monitor_id == storage_key
    assert monitor_id != "('1_switch_snmp_10.0.1.10',)"
    inst = MonitorInstance.objects.get(id=storage_key)
    assert inst.cmdb_id == inst_uuid
    backfill.assert_called_once()
    assert backfill.call_args.args[0]["_id"] == 101
    assert backfill.call_args.args[1] == storage_key


def test_scan_push_does_not_import_monitor_internal_ingest():
    """边界约束：扫描编排不得直连 MonitorModuleIngestService。"""
    import inspect

    import apps.cmdb.services.scan_push_monitor as mod

    source = inspect.getsource(mod)
    assert "from apps.monitor.services.module_ingest import MonitorModuleIngestService" not in source
    assert "push_with_credential" in source


def test_repeat_push_skips_when_ingest_reports_already_present(mocker):
    execution, known, _unknown = _scan_with_hits()
    ingest = _patch_monitor_ingest(
        mocker,
        return_value={"id": "m1", "created": False, "updated": False, "skipped": True},
    )
    mocker.patch(
        "apps.cmdb.services.scan_push_monitor.InstanceManage.query_entity_by_uuids",
        return_value=[
            {
                "_id": 101,
                "inst_uuid": UUID_SWITCH,
                "ip_addr": "10.0.1.10",
                "model_id": "switch",
            }
        ],
    )
    mocker.patch(
        "apps.cmdb.services.module_push.CmdbToMonitorPushService._backfill_monitor_id",
        return_value={},
    )

    result = ScanPushMonitorService.push(execution, [known.id], operator="alice")

    assert result["pushed"] == 0
    assert result["skipped"] == 1
    assert result["failed"] == 0
    assert result["items"][0]["reason"] == "already_in_monitor"
    ingest.assert_called_once()


def test_actor_context_wire_is_json_serializable():
    """RPC 信封不得夹带 CurrentTeamDataScope / request。"""
    import json

    from django.core.serializers.json import DjangoJSONEncoder

    from apps.core.utils.current_team_scope import CurrentTeamDataScope, actor_context_to_wire, hydrate_actor_context_data_scope

    scope = CurrentTeamDataScope(
        current_team=1,
        data_team_ids=frozenset({1, 2}),
        include_children=True,
        username="alice",
        domain="domain.com",
        is_superuser=False,
    )
    wired = actor_context_to_wire(
        {
            "username": "alice",
            "domain": "domain.com",
            "current_team": 1,
            "include_children": True,
            "is_superuser": False,
            "group_list": [1],
            "data_scope": scope,
            "request": object(),
        }
    )
    assert wired is not None
    json.dumps(wired, cls=DjangoJSONEncoder)
    assert "data_scope" not in wired
    assert "request" not in wired
    assert wired["data_team_ids"] == [1, 2]

    hydrated = {"username": "alice", "domain": "domain.com", **wired}
    scope2 = hydrate_actor_context_data_scope(hydrated)
    assert scope2 is not None
    assert scope2.data_team_ids == frozenset({1, 2})
    assert isinstance(hydrated["data_scope"], CurrentTeamDataScope)
