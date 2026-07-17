"""节点管理同步空源与单次运行模型快照行为。"""

from unittest import mock

import pytest
from django.utils import timezone

from apps.cmdb.models import NodeMgmtSyncConfig, NodeMgmtSyncRun
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService


@pytest.fixture
def config(db):
    return NodeMgmtSyncConfig.objects.create(
        name="节点管理同步",
        is_builtin=True,
        auto_sync_enabled=True,
        auto_collect_enabled=True,
    )


def _patch_sync_boundaries(mocker, *, raw_nodes):
    mocker.patch.object(NodeMgmtSyncService, "_cloud_region_name_map", return_value={1: "华东"})
    mocker.patch.object(NodeMgmtSyncService, "_fetch_node_mgmt_pages", return_value=raw_nodes)
    mocker.patch.object(NodeMgmtSyncService, "_load_existing_host_map", return_value={})
    mocker.patch.object(NodeMgmtSyncService, "_pick_access_point", return_value={"id": "ap-1"})
    mocker.patch.object(NodeMgmtSyncService, "_query_region_host_instances", return_value=[])
    mocker.patch.object(NodeMgmtSyncService, "_ensure_region_collect_task", return_value=mock.MagicMock())
    mocker.patch.object(NodeMgmtSyncService, "_persist_hosts", return_value={
        "add": 0,
        "add_success": 0,
        "add_error": 0,
        "update": 0,
        "update_success": 0,
        "update_error": 0,
        "add_data": [],
        "update_data": [],
        "errors": [],
        "changed_instance_ids": [],
    })
    mocker.patch("apps.cmdb.services.node_mgmt_sync_reconciler.NodeMgmtSyncReconciler.reconcile")


@pytest.mark.django_db
def test_node_source_empty_is_blocked_without_advancing_last_sync(mocker, config):
    _patch_sync_boundaries(mocker, raw_nodes=[])
    NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_SUCCESS,
        detail_json={"config_version": config.version},
    )

    result = NodeMgmtSyncService.sync_hosts()

    config.refresh_from_db()
    run = config.runs.latest("created_at")
    assert result["status"] == NodeMgmtSyncRun.STATUS_BLOCKED
    assert run.reason_code == "NODE_SOURCE_EMPTY"
    assert run.summary_json["all"] == 0
    assert run.detail_json["source_total"] == 0
    assert run.detail_json["invalid_node_count"] == 0
    assert config.last_sync_at is None
    assert NodeMgmtSyncService._has_current_successful_sync(config) is False

    NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS,
        detail_json={"config_version": config.version},
    )
    NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_FAILED,
        reason_code="RUN_FAILED",
        detail_json={"config_version": config.version},
    )

    assert NodeMgmtSyncService._has_current_successful_sync(config) is True


@pytest.mark.django_db
def test_all_invalid_regions_are_blocked_with_distinct_sanitized_reason(mocker, config):
    _patch_sync_boundaries(
        mocker,
        raw_nodes=[
            {"id": "node-a", "ip": "10.0.0.1", "cloud_region_id": "invalid", "password": "secret-a"},
            {"id": "node-b", "ip": "10.0.0.2", "cloud_region_id": None, "token": "secret-b"},
        ],
    )

    result = NodeMgmtSyncService.sync_hosts()

    config.refresh_from_db()
    run = config.runs.latest("created_at")
    assert result["status"] == NodeMgmtSyncRun.STATUS_BLOCKED
    assert run.reason_code == "NO_VALID_NODES"
    assert run.summary_json["all"] == 0
    assert run.detail_json["source_total"] == 2
    assert run.detail_json["invalid_node_count"] == 2
    assert "secret-a" not in str(run.detail_json)
    assert "secret-b" not in str(run.detail_json)
    assert config.last_sync_at is None
    assert NodeMgmtSyncService._has_current_successful_sync(config) is False


@pytest.mark.django_db
def test_partial_valid_source_still_syncs_and_queries_host_schema_once_per_run(mocker, config):
    valid_nodes = [
        {
            "id": f"node-{index}",
            "name": f"node-{index}",
            "ip": f"10.0.0.{index}",
            "cloud_region_id": 1,
            "operating_system": "Ubuntu Linux",
        }
        for index in range(1, 51)
    ]
    _patch_sync_boundaries(
        mocker,
        raw_nodes=[*valid_nodes, {"id": "node-invalid", "ip": "10.0.1.1", "cloud_region_id": "invalid"}],
    )
    search_model = mocker.patch.object(
        NodeMgmtSyncService,
        "_host_attr_map",
        return_value={"os_type": {"attr_id": "os_type", "options": [{"id": "linux-new", "name": "Linux"}]}},
    )
    resolve_options = mocker.patch(
        "apps.cmdb.services.node_mgmt_sync_service.ModelManage.resolve_runtime_enum_options",
        side_effect=lambda attr: attr["options"],
    )

    result = NodeMgmtSyncService.sync_hosts()

    run = config.runs.latest("created_at")
    assert result["status"] == NodeMgmtSyncRun.STATUS_SUCCESS
    assert run.detail_json["source_total"] == 51
    assert run.detail_json["invalid_node_count"] == 1
    assert run.detail_json["raw_data"]["data"][0]["os_type"] == "linux-new"
    search_model.assert_called_once_with()
    resolve_options.assert_called_once()
    config.refresh_from_db()
    assert config.last_sync_at is not None


@pytest.mark.django_db
def test_full_retry_reloads_schema_once_for_each_run(mocker, config):
    _patch_sync_boundaries(
        mocker,
        raw_nodes=[
            {"id": "node-a", "name": "node-a", "ip": "10.0.0.1", "cloud_region_id": 1, "operating_system": "Linux"},
        ],
    )
    attr_maps = [
        {"os_type": {"options": [{"id": "linux-v1", "name": "Linux"}]}},
        {"os_type": {"options": [{"id": "linux-v2", "name": "Linux"}]}},
    ]
    search_model = mocker.patch.object(NodeMgmtSyncService, "_host_attr_map", side_effect=attr_maps)
    resolve_options = mocker.patch(
        "apps.cmdb.services.node_mgmt_sync_service.ModelManage.resolve_runtime_enum_options",
        side_effect=lambda attr: attr["options"],
    )

    first = NodeMgmtSyncService.sync_hosts()
    second = NodeMgmtSyncService.sync_hosts()

    runs = list(config.runs.order_by("created_at"))
    assert first["status"] == NodeMgmtSyncRun.STATUS_SUCCESS
    assert second["status"] == NodeMgmtSyncRun.STATUS_SUCCESS
    assert runs[0].detail_json["raw_data"]["data"][0]["os_type"] == "linux-v1"
    assert runs[1].detail_json["raw_data"]["data"][0]["os_type"] == "linux-v2"
    assert search_model.call_count == 2
    assert resolve_options.call_count == 2


@pytest.mark.django_db
def test_empty_source_remains_authoritative_after_newer_non_authoritative_noise(config):
    NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_SUCCESS,
        detail_json={"config_version": config.version},
    )
    NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_BLOCKED,
        reason_code="NODE_SOURCE_EMPTY",
        detail_json={"config_version": config.version},
    )
    for status, reason_code in (
        (NodeMgmtSyncRun.STATUS_BLOCKED, "RUN_ALREADY_ACTIVE"),
        (NodeMgmtSyncRun.STATUS_FAILED, "RUN_FAILED"),
        (NodeMgmtSyncRun.STATUS_TIMEOUT, "RUN_TIMEOUT"),
    ):
        NodeMgmtSyncRun.objects.create(
            task=config,
            run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
            status=status,
            reason_code=reason_code,
            detail_json={"config_version": config.version},
        )

    assert NodeMgmtSyncService._has_current_successful_sync(config) is False


@pytest.mark.django_db
def test_authoritative_sync_tie_is_broken_by_primary_key(config):
    same_time = timezone.now()
    success = NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS,
        detail_json={"config_version": config.version},
    )
    empty = NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_BLOCKED,
        reason_code="NO_VALID_NODES",
        detail_json={"config_version": config.version},
    )
    NodeMgmtSyncRun.objects.filter(pk__in=(success.pk, empty.pk)).update(
        created_at=same_time
    )

    assert empty.pk > success.pk
    assert NodeMgmtSyncService._has_current_successful_sync(config) is False
