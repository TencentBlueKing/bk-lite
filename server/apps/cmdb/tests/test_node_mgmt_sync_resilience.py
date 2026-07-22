"""NodeMgmtSyncService 采集/同步链路的容错性测试。

覆盖 P0 稳定性修复：
1. 编排端任意步骤异常时，运行记录必须标记为 FAILED 并写 finished_at，
   不能永久停留在 RUNNING（否则前端把失败伪装成进行中）。
2. 单个坏节点/坏采集任务不能中断整批同步/采集。
"""
from unittest import mock

import pytest
from django.utils import timezone

from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.models import NodeMgmtSyncConfig, NodeMgmtSyncRun
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.core.utils.web_utils import WebUtils

SERVICE = "apps.cmdb.services.node_mgmt_sync_service"


@pytest.fixture
def sync_config(db):
    config = NodeMgmtSyncConfig.objects.create(name="节点管理同步", is_builtin=True)
    NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_SUCCESS,
        started_at=timezone.now(),
        finished_at=timezone.now(),
        detail_json={"config_version": config.version},
    )
    return config


def _collect_task(region_id):
    return CollectModels.objects.create(
        name=f"task-{region_id}",
        task_type="host",
        driver_type="job",
        model_id="host",
        cycle_value_type="cycle",
        access_point=[{"id": f"ap-{region_id}"}],
        system_code=f"{NodeMgmtSyncService.SYSTEM_TASK_PREFIX}{region_id}",
        is_system=True,
    )


@pytest.mark.django_db
def test_sync_hosts_marks_run_failed_when_fetch_raises(sync_config):
    with mock.patch.object(
        NodeMgmtSyncService, "_fetch_non_container_nodes", side_effect=RuntimeError("fetch boom")
    ):
        with pytest.raises(RuntimeError, match="fetch boom"):
            NodeMgmtSyncService.sync_hosts()

    run = NodeMgmtSyncRun.objects.filter(run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC).latest("created_at")
    assert run.status == NodeMgmtSyncRun.STATUS_FAILED
    assert run.finished_at is not None
    assert run.error_message == "节点管理同步失败：RuntimeError"
    assert "fetch boom" not in run.error_message


def test_fetch_node_mgmt_pages_RPC异常只暴露稳定码且日志不泄露敏感详情(mocker, caplog):
    rpc = mocker.MagicMock()
    rpc.node_list.side_effect = RuntimeError("secret-node-token=raw-sensitive-value")
    mocker.patch.object(NodeMgmtSyncService, "_node_mgmt_client", return_value=rpc)

    with pytest.raises(RuntimeError) as error:
        NodeMgmtSyncService._fetch_node_mgmt_pages({})

    assert str(error.value) == "NODE_QUERY_FAILED: RuntimeError"
    assert "raw-sensitive-value" not in caplog.text
    assert "raw-sensitive-value" not in str(error.value)
    assert len(str(error.value)) <= 255


@pytest.mark.django_db
def test_sync_hosts_节点源超预算时不进入持久化(sync_config, mocker):
    rpc = mocker.MagicMock()
    rpc.cloud_region_list.return_value = [{"id": 1, "name": "华东"}]
    rpc.node_list.return_value = {
        "count": 2,
        "nodes": [
            {"id": "n-1", "ip": "10.0.0.1", "cloud_region_id": 1},
            {"id": "n-2", "ip": "10.0.0.2", "cloud_region_id": 1},
        ],
    }
    mocker.patch.object(NodeMgmtSyncService, "MAX_NODE_COUNT", 1)
    mocker.patch.object(NodeMgmtSyncService, "_node_mgmt_client", return_value=rpc)
    persist_hosts = mocker.patch.object(NodeMgmtSyncService, "_persist_hosts")

    with pytest.raises(RuntimeError, match="^NODE_COUNT_LIMIT_EXCEEDED$"):
        NodeMgmtSyncService.sync_hosts()

    persist_hosts.assert_not_called()
    run = NodeMgmtSyncRun.objects.filter(run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC).latest("created_at")
    assert run.status == NodeMgmtSyncRun.STATUS_FAILED
    assert run.active_scope is None
    assert run.reason_code == "RUN_FAILED"
    assert run.error_message == "节点管理同步失败：NodeMgmtSyncError"


@pytest.mark.django_db
def test_sync_hosts_continues_past_single_node_failure(sync_config):
    nodes = [
        {"ip": "10.0.0.1", "cloud_region_id": 1, "organization_ids": []},
        {"ip": "10.0.0.2", "cloud_region_id": 1, "organization_ids": []},
    ]
    payloads = {
        "10.0.0.1": {"ip_addr": "10.0.0.1", "organization": []},
        "10.0.0.2": {"ip_addr": "10.0.0.2", "organization": []},
    }

    with mock.patch.object(NodeMgmtSyncService, "_fetch_non_container_nodes", return_value=nodes), \
            mock.patch.object(NodeMgmtSyncService, "_group_nodes_by_region", return_value={1: nodes}), \
            mock.patch.object(NodeMgmtSyncService, "_pick_access_point", return_value={"id": "ap-1"}), \
            mock.patch.object(NodeMgmtSyncService, "_normalize_org_ids", return_value=[]), \
            mock.patch.object(NodeMgmtSyncService, "_load_existing_host_map", return_value={}), \
            mock.patch.object(NodeMgmtSyncService, "_host_attr_map", return_value={}), \
            mock.patch.object(NodeMgmtSyncService, "_build_host_instance_payload", side_effect=lambda node, collect_task_id=0, **kwargs: payloads[node["ip"]]), \
            mock.patch.object(NodeMgmtSyncService, "_query_region_host_instances", return_value=[]), \
            mock.patch.object(NodeMgmtSyncService, "_ensure_region_collect_task", return_value=mock.MagicMock()), \
            mock.patch(f"{SERVICE}.InstanceManage.instance_create", side_effect=[RuntimeError("node boom"), {"_id": "h2"}]):
        result = NodeMgmtSyncService.sync_hosts()

    run = NodeMgmtSyncRun.objects.filter(run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC).latest("created_at")
    # 整批没有被单点异常中断：第二个节点仍然成功落库
    assert run.status == NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS
    assert run.finished_at is not None
    assert run.summary_json["add"] == 1
    assert run.summary_json["add_error"] == 1
    assert result["status"] == NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS


@pytest.mark.django_db
def test_collect_hosts_marks_run_failed_when_listing_raises(sync_config):
    with mock.patch.object(
        NodeMgmtSyncService, "_list_region_collect_tasks", side_effect=RuntimeError("list boom")
    ):
        with pytest.raises(RuntimeError, match="list boom"):
            NodeMgmtSyncService.collect_hosts()

    run = NodeMgmtSyncRun.objects.filter(run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT).latest("created_at")
    assert run.status == NodeMgmtSyncRun.STATUS_FAILED
    assert run.finished_at is not None
    assert run.error_message == "节点管理采集失败：RuntimeError"
    assert "list boom" not in run.error_message


@pytest.mark.django_db
def test_collect_hosts_continues_past_single_task_failure(sync_config):
    task_bad = _collect_task(1)
    task_ok = _collect_task(2)

    def accept(task, operator):
        task.task_id = "execution-ok"
        task.exec_status = CollectRunStatusType.RUNNING
        task.save(update_fields=["task_id", "exec_status", "updated_at"])
        return WebUtils.response_success(task.pk)

    with mock.patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[task_bad, task_ok]), mock.patch.object(
        NodeMgmtSyncService, "_execute_collect_task", side_effect=[RuntimeError("exec boom"), accept(task_ok, "system")]
    ):
        NodeMgmtSyncService.collect_hosts()

    run = NodeMgmtSyncRun.objects.filter(run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT).latest("created_at")
    assert run.status == NodeMgmtSyncRun.STATUS_SUBMITTED
    assert run.finished_at is None
    # 坏任务不阻断好任务
    executed_ids = [item["task_id"] for item in run.detail_json.get("executed", [])]
    failed_ids = [item["task_id"] for item in run.detail_json.get("failed", [])]
    assert executed_ids == [task_ok.id]
    assert failed_ids == [task_bad.id]
    assert run.region_states.get(collect_task=task_bad).status == "blocked"
    assert run.region_states.get(collect_task=task_ok).status == "submitted"
