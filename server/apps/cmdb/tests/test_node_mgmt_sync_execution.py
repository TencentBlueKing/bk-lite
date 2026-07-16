from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.cmdb.models import NodeMgmtSyncRun
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncError, NodeMgmtSyncService

pytestmark = pytest.mark.django_db


def test_second_run_is_blocked_while_global_scope_is_held():
    first = NodeMgmtSyncService.acquire_run("sync")
    second = NodeMgmtSyncService.acquire_run("collect")

    assert first.status == NodeMgmtSyncRun.STATUS_RUNNING
    assert first.active_scope == "node_mgmt_sync"
    assert second.status == NodeMgmtSyncRun.STATUS_BLOCKED
    assert second.active_scope is None
    assert second.reason_code == "RUN_ALREADY_ACTIVE"
    assert second.finished_at is not None


def test_stale_run_is_timed_out_and_scope_released():
    stale = NodeMgmtSyncRun.objects.create(
        task=NodeMgmtSyncService.get_task(),
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_RUNNING,
        active_scope="node_mgmt_sync",
        heartbeat_at=timezone.now() - timedelta(minutes=2),
        deadline_at=timezone.now() - timedelta(seconds=1),
    )

    assert NodeMgmtSyncService.recover_stale_runs() == 1

    stale.refresh_from_db()
    assert stale.status == NodeMgmtSyncRun.STATUS_TIMEOUT
    assert stale.reason_code == "RUN_TIMEOUT"
    assert stale.active_scope is None
    assert stale.finished_at is not None


def test_terminal_transition_clears_active_scope():
    run = NodeMgmtSyncService.acquire_run("sync")

    NodeMgmtSyncService.finish_run(run, status=NodeMgmtSyncRun.STATUS_SUCCESS)

    run.refresh_from_db()
    assert run.status == NodeMgmtSyncRun.STATUS_SUCCESS
    assert run.active_scope is None
    assert run.finished_at is not None


def test_heartbeat_rejects_expired_run_and_releases_scope():
    run = NodeMgmtSyncService.acquire_run("sync")
    NodeMgmtSyncRun.objects.filter(pk=run.pk).update(deadline_at=timezone.now() - timedelta(seconds=1))
    run.refresh_from_db()

    with pytest.raises(NodeMgmtSyncError, match="^RUN_TIMEOUT$"):
        NodeMgmtSyncService.heartbeat_run(run)

    run.refresh_from_db()
    assert run.status == NodeMgmtSyncRun.STATUS_TIMEOUT
    assert run.reason_code == "RUN_TIMEOUT"
    assert run.active_scope is None


def test_sync_hosts_returns_blocked_history_without_starting_work():
    NodeMgmtSyncService.acquire_run("collect")

    with mock.patch.object(NodeMgmtSyncService, "_fetch_non_container_nodes") as fetch:
        result = NodeMgmtSyncService.sync_hosts()

    fetch.assert_not_called()
    assert result["status"] == NodeMgmtSyncRun.STATUS_BLOCKED
    assert result["error_message"] == ""


def test_failure_message_is_sanitized_and_scope_is_released():
    run = NodeMgmtSyncService.acquire_run("sync")

    NodeMgmtSyncService.finish_run(
        run, status=NodeMgmtSyncRun.STATUS_FAILED, reason_code="RUN_FAILED", error=RuntimeError("secret-token=raw-sensitive-value"),
    )

    run.refresh_from_db()
    assert run.active_scope is None
    assert run.error_message == "RUN_FAILED: RuntimeError"
    assert "raw-sensitive-value" not in run.error_message


def test_finish_run_does_not_overwrite_existing_terminal_state():
    run = NodeMgmtSyncService.acquire_run("sync")
    NodeMgmtSyncService.finish_run(
        run, status=NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS,
    )

    NodeMgmtSyncService.finish_run(
        run, status=NodeMgmtSyncRun.STATUS_FAILED, reason_code="RUN_FAILED",
    )

    run.refresh_from_db()
    assert run.status == NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS


def test_task_entry_recovers_stale_runs_before_sync(mocker):
    from apps.cmdb.tasks.node_mgmt_sync import run_sync

    recover = mocker.patch.object(NodeMgmtSyncService, "recover_stale_runs")
    trigger = mocker.patch.object(NodeMgmtSyncService, "trigger_sync", return_value={"status": "success"})

    assert run_sync() == {"status": "success"}
    recover.assert_called_once_with()
    trigger.assert_called_once_with()


def test_task_entry_recovers_stale_runs_before_collect(mocker):
    from apps.cmdb.tasks.node_mgmt_sync import run_collect

    recover = mocker.patch.object(NodeMgmtSyncService, "recover_stale_runs")
    trigger = mocker.patch.object(NodeMgmtSyncService, "trigger_collect", return_value={"status": "success"})

    assert run_collect() == {"status": "success"}
    recover.assert_called_once_with()
    trigger.assert_called_once_with()


def test_access_point_pagination_uses_run_deadline_and_heartbeat(mocker):
    run = NodeMgmtSyncService.acquire_run("sync")
    mocker.patch.object(NodeMgmtSyncService, "_cloud_region_name_map", return_value={})
    fetch = mocker.patch.object(NodeMgmtSyncService, "_fetch_node_mgmt_pages", return_value=[])

    assert NodeMgmtSyncService._pick_access_point(1, run=run) is None

    fetch.assert_called_once_with(
        {"cloud_region_id": 1, "is_container": True}, deadline_at=run.deadline_at, run=run,
    )


def test_collect_hosts_returns_blocked_history_without_submitting_work():
    NodeMgmtSyncService.acquire_run("sync")

    result = NodeMgmtSyncService.collect_hosts()

    assert result["status"] == NodeMgmtSyncRun.STATUS_BLOCKED


def test_finish_run_rejects_non_terminal_status():
    run = NodeMgmtSyncService.acquire_run("sync")

    with pytest.raises(ValueError, match="terminal status"):
        NodeMgmtSyncService.finish_run(run, status=NodeMgmtSyncRun.STATUS_RUNNING)


def test_heartbeat_rejects_finished_lease():
    run = NodeMgmtSyncService.acquire_run("sync")
    NodeMgmtSyncService.finish_run(run, status=NodeMgmtSyncRun.STATUS_SUCCESS)

    with pytest.raises(NodeMgmtSyncError, match="^RUN_NOT_ACTIVE$"):
        NodeMgmtSyncService.heartbeat_run(run)


def test_pagination_refreshes_run_heartbeat(mocker):
    run = NodeMgmtSyncService.acquire_run("sync")
    rpc = mocker.MagicMock()
    rpc.node_list.return_value = {"count": 0, "nodes": []}
    mocker.patch.object(NodeMgmtSyncService, "_node_mgmt_client", return_value=rpc)
    heartbeat = mocker.patch.object(NodeMgmtSyncService, "heartbeat_run")

    assert NodeMgmtSyncService._fetch_node_mgmt_pages({}, run=run) == []

    heartbeat.assert_called_once_with(run)


def test_celery_entries_preserve_external_return_contracts(mocker):
    from apps.cmdb.tasks import celery_tasks

    mocker.patch.object(celery_tasks, "run_sync", return_value={"status": "success"})
    mocker.patch.object(celery_tasks, "run_collect", return_value={"status": "success"})

    assert celery_tasks.sync_node_mgmt_hosts() == {"status": "success"}
    assert celery_tasks.collect_node_mgmt_hosts() is None


@pytest.mark.parametrize("task_name", ["sync_node_mgmt_hosts", "collect_node_mgmt_hosts"])
def test_celery_entry_error_log_is_sanitized(mocker, caplog, task_name):
    from apps.cmdb.tasks import celery_tasks

    helper_name = "run_sync" if task_name.startswith("sync") else "run_collect"
    mocker.patch.object(
        celery_tasks, helper_name, side_effect=RuntimeError("secret-token=raw-sensitive-value"),
    )

    with pytest.raises(RuntimeError, match="raw-sensitive-value"):
        getattr(celery_tasks, task_name)()

    assert "raw-sensitive-value" not in caplog.text
    assert "RuntimeError" in caplog.text
