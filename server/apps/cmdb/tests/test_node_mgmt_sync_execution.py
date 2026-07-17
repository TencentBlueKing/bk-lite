from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

import pytest
from django.db import connection
from django.db.models.query import QuerySet
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.cmdb.models import NodeMgmtSyncConfig, NodeMgmtSyncRun
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler
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


@pytest.mark.parametrize(
    ("run_type", "timestamp_field", "status"),
    [
        (NodeMgmtSyncRun.RUN_TYPE_SYNC, "last_sync_at", NodeMgmtSyncRun.STATUS_SUCCESS),
        (NodeMgmtSyncRun.RUN_TYPE_SYNC, "last_sync_at", NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS),
        (NodeMgmtSyncRun.RUN_TYPE_COLLECT, "last_collect_at", NodeMgmtSyncRun.STATUS_SUCCESS),
        (NodeMgmtSyncRun.RUN_TYPE_COLLECT, "last_collect_at", NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS),
    ],
)
def test_successful_finish_advances_matching_config_timestamp(run_type, timestamp_field, status):
    task = NodeMgmtSyncService.get_task()
    run = NodeMgmtSyncService.acquire_run(run_type, task=task)

    NodeMgmtSyncService.finish_run(
        run, status=status,
    )

    task.refresh_from_db()
    assert getattr(task, timestamp_field) == run.finished_at


@pytest.mark.parametrize(
    ("run_type", "timestamp_field"), [(NodeMgmtSyncRun.RUN_TYPE_SYNC, "last_sync_at"), (NodeMgmtSyncRun.RUN_TYPE_COLLECT, "last_collect_at"),],
)
def test_delayed_older_finish_cannot_overwrite_newer_config_timestamp(run_type, timestamp_field):
    task = NodeMgmtSyncService.get_task()
    newer_finished_at = timezone.now() + timedelta(minutes=10)
    setattr(task, timestamp_field, newer_finished_at)
    task.save(update_fields=[timestamp_field, "updated_at"])
    delayed_old_run = NodeMgmtSyncService.acquire_run(run_type, task=task)

    NodeMgmtSyncService.finish_run(
        delayed_old_run, status=NodeMgmtSyncRun.STATUS_SUCCESS,
    )

    task.refresh_from_db()
    assert delayed_old_run.finished_at < newer_finished_at
    assert getattr(task, timestamp_field) == newer_finished_at


@pytest.mark.parametrize(
    "status", [NodeMgmtSyncRun.STATUS_SUCCESS, NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS],
)
def test_successful_finish_and_config_timestamp_update_share_transaction(mocker, status):
    run = NodeMgmtSyncService.acquire_run(NodeMgmtSyncRun.RUN_TYPE_SYNC)
    original_update = QuerySet.update

    def fail_config_update(queryset, **kwargs):
        if queryset.model is NodeMgmtSyncConfig:
            raise RuntimeError("config timestamp write failed")
        return original_update(queryset, **kwargs)

    mocker.patch.object(QuerySet, "update", autospec=True, side_effect=fail_config_update)

    with pytest.raises(RuntimeError, match="config timestamp write failed"):
        NodeMgmtSyncService.finish_run(
            run, status=status,
        )

    run.refresh_from_db()
    assert run.status == NodeMgmtSyncRun.STATUS_RUNNING
    assert run.active_scope == NodeMgmtSyncService.ACTIVE_SCOPE


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


def _expire_active_run():
    NodeMgmtSyncRun.objects.filter(active_scope=NodeMgmtSyncService.ACTIVE_SCOPE).update(deadline_at=timezone.now() - timedelta(seconds=1))


def _mark_current_sync_success(task=None):
    task = task or NodeMgmtSyncService.get_task()
    return NodeMgmtSyncRun.objects.create(
        task=task,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_SUCCESS,
        started_at=timezone.now(),
        finished_at=timezone.now(),
        detail_json={"config_version": task.version},
    )


def _assert_latest_run_timed_out(run_type):
    run = NodeMgmtSyncRun.objects.filter(run_type=run_type).latest("created_at")
    assert run.status == NodeMgmtSyncRun.STATUS_TIMEOUT
    assert run.reason_code == NodeMgmtSyncService.REASON_TIMEOUT
    assert run.active_scope is None
    return run


def test_node_query_exception_crossing_deadline_prefers_timeout(mocker):
    rpc = mocker.MagicMock()
    rpc.cloud_region_list.return_value = []

    def expire_then_raise(_payload):
        _expire_active_run()
        raise RuntimeError("node query failed after deadline")

    rpc.node_list.side_effect = expire_then_raise
    mocker.patch.object(NodeMgmtSyncService, "_node_mgmt_client", return_value=rpc)

    with pytest.raises(NodeMgmtSyncError, match="^NODE_QUERY_FAILED: RuntimeError$"):
        NodeMgmtSyncService.sync_hosts()

    run = _assert_latest_run_timed_out(NodeMgmtSyncRun.RUN_TYPE_SYNC)
    NodeMgmtSyncService.finish_run(
        run, status=NodeMgmtSyncRun.STATUS_FAILED, reason_code="RUN_FAILED", error=RuntimeError("late old worker"),
    )
    _assert_latest_run_timed_out(NodeMgmtSyncRun.RUN_TYPE_SYNC)


def test_cloud_region_exception_crossing_deadline_prefers_timeout(mocker):
    rpc = mocker.MagicMock()

    def expire_then_raise():
        _expire_active_run()
        raise RuntimeError("region query failed after deadline")

    rpc.cloud_region_list.side_effect = expire_then_raise
    mocker.patch.object(NodeMgmtSyncService, "_node_mgmt_client", return_value=rpc)

    with pytest.raises(RuntimeError, match="region query failed after deadline"):
        NodeMgmtSyncService.sync_hosts()

    _assert_latest_run_timed_out(NodeMgmtSyncRun.RUN_TYPE_SYNC)


def test_collect_external_exception_crossing_deadline_prefers_timeout(mocker):
    _mark_current_sync_success()

    def expire_then_raise():
        _expire_active_run()
        raise RuntimeError("collect list failed after deadline")

    mocker.patch.object(
        NodeMgmtSyncService, "_list_region_collect_tasks", side_effect=expire_then_raise,
    )

    with pytest.raises(RuntimeError, match="collect list failed after deadline"):
        NodeMgmtSyncService.collect_hosts()

    _assert_latest_run_timed_out(NodeMgmtSyncRun.RUN_TYPE_COLLECT)


def test_persist_hosts_stops_after_first_external_write_expires_lease(mocker):
    run = NodeMgmtSyncService.acquire_run("sync")
    desired_hosts = [
        {"ip_addr": "10.0.0.1", "cloud": 1, "organization": [1]},
        {"ip_addr": "10.0.0.2", "cloud": 1, "organization": [1]},
    ]

    def expire_after_create(*args, **kwargs):
        NodeMgmtSyncRun.objects.filter(pk=run.pk).update(deadline_at=timezone.now() - timedelta(seconds=1))
        return {"_id": 1, **args[1]}

    create = mocker.patch("apps.cmdb.services.node_mgmt_sync_service.InstanceManage.instance_create", side_effect=expire_after_create,)

    with pytest.raises(NodeMgmtSyncError, match="^RUN_TIMEOUT$"):
        NodeMgmtSyncService._persist_hosts(
            desired_hosts, existing_hosts={}, operator="system", operation_id=str(run.generation), run=run,
        )

    assert create.call_count == 1
    run.refresh_from_db()
    assert run.status == NodeMgmtSyncRun.STATUS_TIMEOUT
    assert run.active_scope is None


def test_collect_submit_crossing_deadline_cannot_finish_success(mocker):
    run = NodeMgmtSyncService.acquire_run("collect")
    task_config = NodeMgmtSyncService.get_task()
    collect_task = CollectModels.objects.create(
        name="region-1",
        task_type="host",
        driver_type="job",
        model_id="host",
        cycle_value_type="cycle",
        access_point=[{"id": 1}],
        system_code=f"{NodeMgmtSyncService.SYSTEM_TASK_PREFIX}1",
        is_system=True,
    )
    mocker.patch.object(NodeMgmtSyncService, "_list_region_collect_tasks", return_value=[collect_task])

    def expire_after_submit(task, operator):
        NodeMgmtSyncRun.objects.filter(pk=run.pk).update(deadline_at=timezone.now() - timedelta(seconds=1))

    submit = mocker.patch.object(NodeMgmtSyncService, "_execute_collect_task", side_effect=expire_after_submit,)

    with pytest.raises(NodeMgmtSyncError, match="^RUN_TIMEOUT$"):
        NodeMgmtSyncService._do_collect_hosts(run, task_config)

    submit.assert_called_once_with(collect_task, "system")
    run.refresh_from_db()
    assert run.status == NodeMgmtSyncRun.STATUS_TIMEOUT
    assert run.active_scope is None


def test_recovered_stale_run_cannot_be_overwritten_by_old_worker_finish():
    run = NodeMgmtSyncService.acquire_run("sync")
    NodeMgmtSyncRun.objects.filter(pk=run.pk).update(deadline_at=timezone.now() - timedelta(seconds=1))

    assert NodeMgmtSyncService.recover_stale_runs() == 1
    with pytest.raises(NodeMgmtSyncError, match="^RUN_TIMEOUT$"):
        NodeMgmtSyncService.finish_run(
            run, status=NodeMgmtSyncRun.STATUS_SUCCESS, summary_json={"all": 2},
        )

    run.refresh_from_db()
    assert run.status == NodeMgmtSyncRun.STATUS_TIMEOUT
    assert run.reason_code == "RUN_TIMEOUT"
    assert run.summary_json == {}


def test_recover_stale_runs_uses_single_deadline_guarded_update():
    run = NodeMgmtSyncService.acquire_run("sync")
    NodeMgmtSyncRun.objects.filter(pk=run.pk).update(deadline_at=timezone.now() - timedelta(seconds=1))

    with CaptureQueriesContext(connection) as queries:
        assert NodeMgmtSyncService.recover_stale_runs() == 1

    updates = [query["sql"] for query in queries if query["sql"].lstrip().upper().startswith("UPDATE")]
    assert len(updates) == 1
    normalized_sql = updates[0].lower()
    assert "deadline_at" in normalized_sql
    assert "active_scope" in normalized_sql
    assert "status" in normalized_sql


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
    _mark_current_sync_success()
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

    assert heartbeat.call_args_list == [mock.call(run), mock.call(run)]


def test_cloud_region_rpc_is_guarded_before_and_after(mocker):
    run = NodeMgmtSyncService.acquire_run("sync")
    rpc = mocker.Mock()
    rpc.cloud_region_list.return_value = [{"id": 1, "name": "region-1"}]
    mocker.patch.object(NodeMgmtSyncService, "_node_mgmt_client", return_value=rpc)
    heartbeat = mocker.patch.object(NodeMgmtSyncService, "heartbeat_run")

    assert NodeMgmtSyncService._cloud_region_name_map(run=run) == {1: "region-1"}

    assert heartbeat.call_args_list == [mock.call(run), mock.call(run)]


def test_existing_collect_task_only_persists_delivery_intent(mocker):
    run = NodeMgmtSyncService.acquire_run("sync")
    collect_task = SimpleNamespace(id=21, instances=[], access_point=[], save=mocker.Mock(),)
    queryset = mocker.Mock()
    queryset.first.return_value = collect_task
    mocker.patch.object(CollectModels.objects, "filter", return_value=queryset)
    mocker.patch.object(
        NodeMgmtSyncService, "_should_repush_collect_task_node_params", return_value=True,
    )
    collect_service = SimpleNamespace(
        should_sync_node_params=mocker.Mock(return_value=True), delete_butch_node_params=mocker.Mock(), push_butch_node_params=mocker.Mock(),
    )
    delivery = mocker.patch.object(NodeMgmtSyncReconciler, "mark_region_delivery_pending")
    heartbeat = mocker.patch.object(NodeMgmtSyncService, "heartbeat_run")

    with mock.patch.dict(
        "sys.modules", {"apps.cmdb.services.collect_service": SimpleNamespace(CollectModelService=collect_service)},
    ):
        result = NodeMgmtSyncService._ensure_region_collect_task(
            cloud_region_id=1, cloud_region_name="region-1", access_point={"id": 1}, team=[1], instances=[{"_id": 1}], interval_minutes=30, run=run,
        )

    assert result is collect_task
    collect_task.save.assert_called_once_with()
    collect_service.should_sync_node_params.assert_called_once_with(collect_task)
    collect_service.delete_butch_node_params.assert_not_called()
    collect_service.push_butch_node_params.assert_not_called()
    delivery.assert_called_once()
    assert heartbeat.call_count == 3


def test_new_collect_task_only_persists_delivery_intent(mocker):
    run = NodeMgmtSyncService.acquire_run("sync")
    collect_task = SimpleNamespace(id=22)
    queryset = mocker.Mock()
    queryset.first.return_value = None
    mocker.patch.object(CollectModels.objects, "filter", return_value=queryset)
    create = mocker.patch.object(CollectModels.objects, "create", return_value=collect_task,)
    collect_service = SimpleNamespace(should_sync_node_params=mocker.Mock(return_value=True), push_butch_node_params=mocker.Mock(),)
    delivery = mocker.patch.object(NodeMgmtSyncReconciler, "mark_region_delivery_pending")
    heartbeat = mocker.patch.object(NodeMgmtSyncService, "heartbeat_run")

    with mock.patch.dict(
        "sys.modules", {"apps.cmdb.services.collect_service": SimpleNamespace(CollectModelService=collect_service)},
    ):
        result = NodeMgmtSyncService._ensure_region_collect_task(
            cloud_region_id=1, cloud_region_name="region-1", access_point={"id": 1}, team=[1], instances=[{"_id": 1}], interval_minutes=30, run=run,
        )

    assert result is collect_task
    create.assert_called_once()
    collect_service.push_butch_node_params.assert_not_called()
    delivery.assert_called_once()
    assert heartbeat.call_count == 3


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
