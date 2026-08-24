"""节点管理主机同步持久化行为测试。"""

from unittest import mock
from uuid import UUID

import pytest

from apps.cmdb.models import NodeMgmtSyncConfig, NodeMgmtSyncRun
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

SERVICE = "apps.cmdb.services.node_mgmt_sync_service"
RECONCILE = "apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile"
GENERATION = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def existing_host():
    return {
        "_id": 7,
        "model_id": "host",
        "inst_name": "old-name",
        "ip_addr": "10.0.0.7",
        "organization": [1],
        "cloud": 2,
        "os_type": "1",
    }


@pytest.fixture
def desired_host():
    return {
        "model_id": "host",
        "inst_name": "new-name",
        "ip_addr": "10.0.0.7",
        "organization": [2],
        "cloud": 2,
        "cloud_id": 2,
        "cloud_name": "华东",
        "os_type": "2",
        "node_id": "node-7",
        "source": "node_mgmt_sync",
        "secret": "must-not-persist",
    }


@pytest.fixture(autouse=True)
def _mute_persist_side_effects(mocker):
    mocker.patch.object(NodeMgmtSyncService, "_ensure_host_node_id_attr")
    mocker.patch.object(NodeMgmtSyncService, "_backfill_node_cmdb_id")


def test_existing_host_diff_calls_instance_update(mocker, existing_host, desired_host):
    update = mocker.patch(f"{SERVICE}.InstanceManage.instance_update", return_value={**existing_host, "inst_name": "new-name"},)

    result = NodeMgmtSyncService._persist_hosts(
        [desired_host], existing_hosts={desired_host["ip_addr"]: existing_host}, operator="system", operation_id=str(GENERATION),
    )

    update.assert_called_once_with(
        user_groups=[],
        roles=[],
        inst_id=existing_host["_id"],
        update_attr={"inst_name": "new-name", "organization": [2], "os_type": "2", "node_id": "node-7"},
        operator="system",
        allowed_org_ids=None,
        skip_permission_check=True,
        operation_id=str(GENERATION),
        schedule_post_actions=False,
    )
    assert result["update"] == 1
    assert result["update_success"] == 1
    assert result["changed_instance_ids"] == [7]


def test_unchanged_host_is_not_written(mocker, existing_host):
    update = mocker.patch(f"{SERVICE}.InstanceManage.instance_update")

    result = NodeMgmtSyncService._persist_hosts(
        [{**existing_host, "cloud_id": 2, "cloud_name": "ignored metadata"}],
        existing_hosts={(existing_host["ip_addr"], 2): existing_host},
        operator="system",
        operation_id=str(GENERATION),
    )

    update.assert_not_called()
    assert result["update"] == 0
    assert result["update_success"] == 0
    assert result["changed_instance_ids"] == []


def test_update_failure_is_counted_and_sanitized(mocker, caplog, existing_host, desired_host):
    mocker.patch(
        f"{SERVICE}.InstanceManage.instance_update", side_effect=RuntimeError("write failed secret-token=raw-sensitive-value"),
    )

    result = NodeMgmtSyncService._persist_hosts(
        [desired_host], existing_hosts={desired_host["ip_addr"]: existing_host}, operator="system", operation_id=str(GENERATION),
    )

    assert result["update"] == 1
    assert result["update_error"] == 1
    assert result["update_success"] == 0
    assert result["errors"] == [{"operation": "update", "error": "HOST_UPDATE_FAILED: RuntimeError"}]
    assert "raw-sensitive-value" not in caplog.text
    assert "raw-sensitive-value" not in str(result)


def test_new_host_success_is_counted_and_uses_generation(mocker, desired_host):
    create = mocker.patch(f"{SERVICE}.InstanceManage.instance_create", return_value={**desired_host, "_id": 8},)
    persisted_host = {
        "inst_name": "new-name",
        "ip_addr": "10.0.0.7",
        "organization": [2],
        "cloud": 2,
        "os_type": "2",
        "node_id": "node-7",
    }

    result = NodeMgmtSyncService._persist_hosts([desired_host], existing_hosts={}, operator="system", operation_id=str(GENERATION),)

    create.assert_called_once_with(
        "host", persisted_host, operator="system", allowed_org_ids=[2], operation_id=str(GENERATION), schedule_post_actions=False,
    )
    assert result["add"] == 1
    assert result["add_success"] == 1
    assert result["add_error"] == 0
    assert result["add_data"] == [
        {
            "inst_name": "new-name",
            "ip_addr": "10.0.0.7",
            "organization": [2],
            "cloud": 2,
            "os_type": "2",
            "_id": 8,
        }
    ]
    assert result["changed_instance_ids"] == [8]


@pytest.fixture
def sync_run(db):
    config = NodeMgmtSyncConfig.objects.create(name="节点管理同步", is_builtin=True)
    run = NodeMgmtSyncService.acquire_run(NodeMgmtSyncRun.RUN_TYPE_SYNC, task=config,)
    return run, config


def _sync_mocks(mocker, nodes, existing_hosts):
    mocker.patch.object(NodeMgmtSyncService, "_fetch_non_container_nodes", return_value=nodes)
    mocker.patch.object(NodeMgmtSyncService, "_group_nodes_by_region", return_value={2: nodes})
    mocker.patch.object(NodeMgmtSyncService, "_pick_access_point", return_value={"id": "ap-2"})
    mocker.patch.object(NodeMgmtSyncService, "_normalize_org_ids", side_effect=lambda value: value or [])
    existing_loader = mocker.patch.object(NodeMgmtSyncService, "_load_existing_host_map", return_value=existing_hosts)
    mocker.patch.object(NodeMgmtSyncService, "_query_region_host_instances", return_value=[])
    mocker.patch.object(NodeMgmtSyncService, "_ensure_region_collect_task", return_value=mock.MagicMock())
    mocker.patch.object(NodeMgmtSyncService, "_host_attr_map", return_value={})
    mocker.patch.object(NodeMgmtSyncService, "_ensure_host_node_id_attr")
    mocker.patch.object(NodeMgmtSyncService, "_backfill_node_cmdb_id")
    return existing_loader


@pytest.mark.django_db
def test_retry_reloads_persisted_hosts_without_duplicate_create(mocker, sync_run, desired_host):
    run, config = sync_run
    nodes = [{"ip": desired_host["ip_addr"], "cloud_region_id": 2, "organization_ids": [2]}]
    persisted_host = {
        "_id": 8,
        "inst_name": "new-name",
        "ip_addr": "10.0.0.7",
        "organization": [2],
        "cloud": 2,
        "os_type": "2",
        "node_id": "node-7",
    }
    existing_loader = _sync_mocks(mocker, nodes, {})
    existing_loader.side_effect = [{}, {(desired_host["ip_addr"], 2): persisted_host}]
    mocker.patch.object(NodeMgmtSyncService, "_build_host_instance_payload", return_value=desired_host)
    create = mocker.patch(f"{SERVICE}.InstanceManage.instance_create", return_value={**desired_host, "_id": 8},)
    mocker.patch(RECONCILE)

    first = NodeMgmtSyncService._do_sync_hosts(run, config)
    retry_run = NodeMgmtSyncService.acquire_run(NodeMgmtSyncRun.RUN_TYPE_SYNC, task=config,)
    second = NodeMgmtSyncService._do_sync_hosts(retry_run, config)

    assert first["summary"]["add_success"] == 1
    assert second["summary"]["add"] == 0
    assert second["summary"]["update"] == 0
    assert existing_loader.call_count == 2
    create.assert_called_once()
    retry_run.refresh_from_db()
    forbidden_fields = {"cloud_id", "cloud_name", "node_id", "source", "secret"}
    assert forbidden_fields.isdisjoint(retry_run.detail_json["raw_data"]["data"][0])


@pytest.mark.django_db
def test_update_failure_marks_parent_run_partial_success(mocker, caplog, sync_run, existing_host, desired_host):
    run, config = sync_run
    nodes = [{"ip": desired_host["ip_addr"], "cloud_region_id": 2, "organization_ids": [2]}]
    _sync_mocks(mocker, nodes, {(desired_host["ip_addr"], 2): existing_host})
    mocker.patch.object(NodeMgmtSyncService, "_build_host_instance_payload", return_value=desired_host)
    mocker.patch(
        f"{SERVICE}.InstanceManage.instance_update", side_effect=RuntimeError("write failed secret-token=raw-sensitive-value"),
    )

    result = NodeMgmtSyncService._do_sync_hosts(run, config)

    run.refresh_from_db()
    assert result["status"] == NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS
    assert run.summary_json["update"] == 1
    assert run.summary_json["update_error"] == 1
    assert run.summary_json["update_success"] == 0
    assert run.detail_json["todo"] == [{"operation": "update", "error": "HOST_UPDATE_FAILED: RuntimeError"}]
    assert "raw-sensitive-value" not in caplog.text
    assert "raw-sensitive-value" not in str(run.detail_json)


@pytest.mark.django_db
def test_changed_hosts_schedule_relation_reconcile_once(mocker, sync_run, existing_host, desired_host):
    run, config = sync_run
    new_host = {**desired_host, "ip_addr": "10.0.0.8", "inst_name": "10.0.0.8[华东]", "node_id": "node-8"}
    nodes = [
        {"ip": desired_host["ip_addr"], "cloud_region_id": 2, "organization_ids": [2]},
        {"ip": new_host["ip_addr"], "cloud_region_id": 2, "organization_ids": [2]},
    ]
    _sync_mocks(mocker, nodes, {(desired_host["ip_addr"], 2): existing_host})
    mocker.patch.object(
        NodeMgmtSyncService, "_build_host_instance_payload", side_effect=[desired_host, new_host],
    )
    mocker.patch(
        f"{SERVICE}.InstanceManage.instance_update", return_value={**desired_host, "_id": 7},
    )
    mocker.patch(
        f"{SERVICE}.InstanceManage.instance_create", return_value={**new_host, "_id": 8},
    )
    reconcile = mocker.patch(RECONCILE)

    NodeMgmtSyncService._do_sync_hosts(run, config)

    reconcile.assert_called_once_with([7, 8])


@pytest.mark.django_db
def test_relation_reconcile_failure_marks_parent_partial_and_is_sanitized(mocker, caplog, sync_run, desired_host):
    run, config = sync_run
    nodes = [{"ip": desired_host["ip_addr"], "cloud_region_id": 2, "organization_ids": [2]}]
    _sync_mocks(mocker, nodes, {})
    mocker.patch.object(NodeMgmtSyncService, "_build_host_instance_payload", return_value=desired_host)
    mocker.patch(
        f"{SERVICE}.InstanceManage.instance_create", return_value={**desired_host, "_id": 8},
    )
    mocker.patch(
        RECONCILE, side_effect=RuntimeError("relation failed secret-token=raw-sensitive-value"),
    )

    result = NodeMgmtSyncService._do_sync_hosts(run, config)

    run.refresh_from_db()
    assert result["status"] == NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS
    assert run.summary_json["association_error"] == 1
    assert run.detail_json["todo"] == [{"operation": "relation", "error": "RELATION_RECONCILE_FAILED: RuntimeError"}]
    assert "raw-sensitive-value" not in caplog.text
    assert "raw-sensitive-value" not in str(run.detail_json)


@pytest.mark.django_db
def test_multi_region_sync_loads_existing_hosts_once_and_reuses_snapshot(mocker, sync_run):
    run, config = sync_run
    nodes = [
        {"ip": "10.0.0.1", "cloud_region_id": 1, "organization_ids": []},
        {"ip": "10.0.0.2", "cloud_region_id": 2, "organization_ids": []},
    ]
    existing = {
        ("10.0.0.1", 1): {"_id": 1, "ip_addr": "10.0.0.1", "cloud": 1},
        ("10.0.0.2", 2): {"_id": 2, "ip_addr": "10.0.0.2", "cloud": 2},
    }
    mocker.patch.object(NodeMgmtSyncService, "_fetch_non_container_nodes", return_value=nodes)
    mocker.patch.object(
        NodeMgmtSyncService,
        "_group_nodes_by_region",
        return_value={1: [nodes[0]], 2: [nodes[1]]},
    )
    mocker.patch.object(NodeMgmtSyncService, "_pick_access_point", return_value={"id": "ap"})
    mocker.patch.object(NodeMgmtSyncService, "_host_attr_map", return_value={})
    loader = mocker.patch.object(NodeMgmtSyncService, "_load_existing_host_map", return_value=existing)
    mocker.patch.object(
        NodeMgmtSyncService,
        "_build_host_instance_payload",
        side_effect=[
            {"ip_addr": "10.0.0.1", "cloud": 1},
            {"ip_addr": "10.0.0.2", "cloud": 2},
        ],
    )
    mocker.patch.object(NodeMgmtSyncService, "_ensure_region_collect_task", return_value=mock.MagicMock())
    mocker.patch("apps.cmdb.services.node_mgmt_sync_reconciler.NodeMgmtSyncReconciler.reconcile")

    NodeMgmtSyncService._do_sync_hosts(run, config)

    loader.assert_called_once_with(task_id=0, run=run)


def test_persist_skips_when_ip_or_cloud_missing(mocker, desired_host):
    create = mocker.patch(f"{SERVICE}.InstanceManage.instance_create")
    update = mocker.patch(f"{SERVICE}.InstanceManage.instance_update")

    result = NodeMgmtSyncService._persist_hosts(
        [{**desired_host, "ip_addr": "", "cloud": None}],
        existing_hosts={},
        operator="system",
        operation_id=str(GENERATION),
    )

    create.assert_not_called()
    update.assert_not_called()
    assert result["add"] == 0
    assert result["update"] == 0


def test_persist_skips_when_ip_cloud_bound_to_other_node_id(mocker, desired_host):
    create = mocker.patch(f"{SERVICE}.InstanceManage.instance_create")
    update = mocker.patch(f"{SERVICE}.InstanceManage.instance_update")
    existing = {
        "_id": 9,
        "ip_addr": "10.0.0.7",
        "cloud": 2,
        "node_id": "other-node",
        "inst_name": "10.0.0.7[华东]",
        "organization": [2],
        "os_type": "2",
    }

    result = NodeMgmtSyncService._persist_hosts(
        [desired_host],
        existing_hosts={(desired_host["ip_addr"], 2): existing},
        operator="system",
        operation_id=str(GENERATION),
    )

    create.assert_not_called()
    update.assert_not_called()
    assert result["add"] == 0
    assert result["update"] == 0


def test_persist_matches_by_node_id_even_when_ip_cloud_differs(mocker, desired_host):
    existing = {
        "_id": 7,
        "node_id": "node-7",
        "ip_addr": "10.0.0.9",
        "cloud": 3,
        "inst_name": "old",
        "organization": [1],
        "os_type": "1",
    }
    update = mocker.patch(
        f"{SERVICE}.InstanceManage.instance_update",
        return_value={**existing, **desired_host, "_id": 7},
    )
    create = mocker.patch(f"{SERVICE}.InstanceManage.instance_create")

    result = NodeMgmtSyncService._persist_hosts(
        [desired_host],
        existing_hosts={("10.0.0.9", 3): existing},
        operator="system",
        operation_id=str(GENERATION),
    )

    create.assert_not_called()
    update.assert_called_once()
    assert result["update_success"] == 1


def test_unlink_stale_sidecar_node_id_clears_pointer_keeps_instance(mocker):
    stale_id = "7e1bcd3d738c482fa33530b289d1c444"
    live_id = "7606c5cb3a054c8dbded35a16e98ea33"
    stale = {
        "_id": 1140,
        "ip_addr": "172.16.0.4",
        "cloud": 1,
        "node_id": stale_id,
        "inst_name": "172.16.0.4[default]",
    }
    live = {
        "_id": 1171,
        "ip_addr": "10.77.1.111",
        "cloud": 1,
        "node_id": live_id,
        "inst_name": "10.77.1.111[default]",
    }
    update = mocker.patch(
        "apps.cmdb.services.module_ingest.write_system_link_fields",
        return_value={**stale, "node_id": ""},
    )

    result = NodeMgmtSyncService._unlink_stale_host_node_ids(
        existing_hosts={("172.16.0.4", 1): stale, ("10.77.1.111", 1): live},
        live_node_ids={live_id},
        operator="system",
        operation_id=str(GENERATION),
    )

    update.assert_called_once_with(1140, {"node_id": ""})
    assert result["unlink_success"] == 1
    assert stale["node_id"] == ""
    assert live["node_id"] == live_id


def test_unlink_stale_skips_non_sidecar_node_ids(mocker):
    ipmi = {
        "_id": 1146,
        "ip_addr": "10.78.90.114",
        "cloud": 1,
        "node_id": "ioc-ipmi-15a2a84b91",
        "inst_name": "ioc-ipmi-10.78.90.114",
    }
    update = mocker.patch("apps.cmdb.services.module_ingest.write_system_link_fields")

    result = NodeMgmtSyncService._unlink_stale_host_node_ids(
        existing_hosts={("10.78.90.114", 1): ipmi},
        live_node_ids=set(),
        operator="system",
        operation_id=str(GENERATION),
    )

    update.assert_not_called()
    assert result["unlink_success"] == 0
    assert ipmi["node_id"] == "ioc-ipmi-15a2a84b91"


def test_persist_unique_conflict_updates_existing_instead_of_duplicate(mocker, desired_host):
    from apps.core.exceptions.base_app_exception import BaseAppException

    recovered = {
        "_id": 44,
        "ip_addr": "10.0.0.7",
        "cloud": 2,
        "node_id": "",
        "inst_name": "old-name",
        "organization": [1],
        "os_type": "1",
    }
    mocker.patch(
        f"{SERVICE}.InstanceManage.instance_create",
        side_effect=BaseAppException("ip_addr exist；"),
    )
    mocker.patch.object(
        NodeMgmtSyncService,
        "_recover_host_after_unique_conflict",
        return_value=recovered,
    )
    update = mocker.patch(
        f"{SERVICE}.InstanceManage.instance_update",
        return_value={**recovered, "node_id": "node-7", "_id": 44},
    )

    result = NodeMgmtSyncService._persist_hosts(
        [desired_host],
        existing_hosts={},
        operator="system",
        operation_id=str(GENERATION),
    )

    update.assert_called_once()
    assert update.call_args.kwargs["inst_id"] == 44
    assert update.call_args.kwargs["update_attr"]["node_id"] == "node-7"
    assert result["add"] == 0
    assert result["update_success"] == 1


def test_persist_does_not_write_monitor_id(mocker, existing_host, desired_host):
    existing_host = {**existing_host, "node_id": "node-7", "monitor_id": "mon-keep"}
    update = mocker.patch(
        f"{SERVICE}.InstanceManage.instance_update",
        return_value={**existing_host, "inst_name": "new-name"},
    )

    NodeMgmtSyncService._persist_hosts(
        [{**desired_host, "monitor_id": "mon-new"}],
        existing_hosts={(desired_host["ip_addr"], 2): existing_host},
        operator="system",
        operation_id=str(GENERATION),
    )

    written = update.call_args.kwargs["update_attr"]
    assert "monitor_id" not in written


def test_persist_new_host_backfills_node_cmdb_id(mocker, desired_host):
    mocker.patch(f"{SERVICE}.InstanceManage.instance_create", return_value={**desired_host, "_id": 8})
    backfill = mocker.patch.object(NodeMgmtSyncService, "_backfill_node_cmdb_id")

    NodeMgmtSyncService._persist_hosts(
        [desired_host],
        existing_hosts={},
        operator="system",
        operation_id=str(GENERATION),
    )

    backfill.assert_called_once()
    assert backfill.call_args.kwargs["node_id"] == "node-7"
    assert backfill.call_args.kwargs["cmdb_id"] == 8
    assert backfill.call_args.kwargs["ip"] == "10.0.0.7"
    assert backfill.call_args.kwargs["cloud"] == 2

