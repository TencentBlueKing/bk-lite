"""NodeMgmtSyncService 采集/同步链路的容错性测试。

覆盖 P0 稳定性修复：
1. 编排端任意步骤异常时，运行记录必须标记为 FAILED 并写 finished_at，
   不能永久停留在 RUNNING（否则前端把失败伪装成进行中）。
2. 单个坏节点/坏采集任务不能中断整批同步/采集。
"""
from unittest import mock

import pytest

from apps.cmdb.models import NodeMgmtSyncConfig, NodeMgmtSyncRun
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

SERVICE = "apps.cmdb.services.node_mgmt_sync_service"


@pytest.fixture
def sync_config(db):
    return NodeMgmtSyncConfig.objects.create(name="节点管理同步", is_builtin=True)


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
    assert "fetch boom" in run.error_message


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
            mock.patch.object(NodeMgmtSyncService, "_build_host_instance_payload", side_effect=lambda node, collect_task_id=0: payloads[node["ip"]]), \
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
    assert "list boom" in run.error_message


@pytest.mark.django_db
def test_collect_hosts_continues_past_single_task_failure(sync_config):
    task_ok = mock.MagicMock(id=1, access_point=[{"id": "ap-1"}])
    task_ok.name = "task-1"
    task_bad = mock.MagicMock(id=2, access_point=[{"id": "ap-2"}])
    task_bad.name = "task-2"

    with mock.patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[task_bad, task_ok]), \
            mock.patch.object(NodeMgmtSyncService, "_execute_collect_task", side_effect=[RuntimeError("exec boom"), None]):
        NodeMgmtSyncService.collect_hosts()

    run = NodeMgmtSyncRun.objects.filter(run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT).latest("created_at")
    assert run.status == NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS
    assert run.finished_at is not None
    # 坏任务不阻断好任务
    executed_ids = [item["task_id"] for item in run.detail_json.get("executed", [])]
    failed_ids = [item["task_id"] for item in run.detail_json.get("failed", [])]
    assert executed_ids == [1]
    assert failed_ids == [2]
