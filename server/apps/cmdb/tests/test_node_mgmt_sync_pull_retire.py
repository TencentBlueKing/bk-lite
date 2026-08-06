"""推送联动关闭 NodeMgmtSync 拉取同步的门闩行为。"""

import pytest
from django_celery_beat.models import PeriodicTask

from apps.cmdb.models import NodeMgmtSyncRun
from apps.cmdb.services import node_mgmt_sync_service as node_mgmt_sync_service_mod
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

pytestmark = pytest.mark.django_db


def test_sync_hosts_blocked_when_push_linkage_replaces_pull(mocker):
    assert node_mgmt_sync_service_mod.PUSH_LINKAGE_REPLACES_PULL_SYNC is True

    create = mocker.patch(
        "apps.cmdb.services.node_mgmt_sync_service.InstanceManage.instance_create",
    )
    update = mocker.patch(
        "apps.cmdb.services.node_mgmt_sync_service.InstanceManage.instance_update",
    )
    fetch = mocker.patch.object(NodeMgmtSyncService, "_fetch_non_container_nodes")
    do_sync = mocker.patch.object(NodeMgmtSyncService, "_do_sync_hosts")

    result = NodeMgmtSyncService.sync_hosts()

    fetch.assert_not_called()
    do_sync.assert_not_called()
    create.assert_not_called()
    update.assert_not_called()
    assert result["status"] == NodeMgmtSyncRun.STATUS_BLOCKED
    assert result["reason_code"] == NodeMgmtSyncService.REASON_PUSH_LINKAGE_REPLACES_PULL

    run = NodeMgmtSyncRun.objects.filter(run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC).latest("created_at")
    assert run.status == NodeMgmtSyncRun.STATUS_BLOCKED
    assert run.reason_code == NodeMgmtSyncService.REASON_PUSH_LINKAGE_REPLACES_PULL
    assert run.active_scope is None
    assert run.summary_json.get("skipped") is True


def test_reconciler_does_not_enable_sync_schedule_when_gate_on():
    assert node_mgmt_sync_service_mod.PUSH_LINKAGE_REPLACES_PULL_SYNC is True

    NodeMgmtSyncService.update_task({"auto_sync_enabled": True, "auto_collect_enabled": True})
    payload = NodeMgmtSyncService.get_task_payload(reconcile=True)

    assert payload["auto_sync_enabled"] is True
    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME not in set(
        PeriodicTask.objects.values_list("name", flat=True)
    )
    assert NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME in set(
        PeriodicTask.objects.values_list("name", flat=True)
    )


def test_auto_sync_enabled_defaults_to_false_for_new_config():
    task = NodeMgmtSyncService.get_task()
    assert task.auto_sync_enabled is False
