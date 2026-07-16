from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncConfig, NodeMgmtSyncRegionState, NodeMgmtSyncRun
from apps.cmdb.services.collect_service import CollectModelService
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.core.utils.web_utils import WebUtils

pytestmark = pytest.mark.django_db


@pytest.fixture
def config():
    return NodeMgmtSyncConfig.objects.create(
        auto_sync_enabled=True, auto_collect_enabled=True, schedule_status="healthy", node_config_status="healthy",
    )


def _collect_task(region_id):
    return CollectModels.objects.create(
        name=f"区域采集-{region_id}",
        task_type="host",
        driver_type="job",
        model_id="host",
        cycle_value_type="cycle",
        cycle_value="30",
        scan_cycle="*/30 * * * *",
        instances=[{"ip_addr": f"10.0.0.{region_id}"}],
        access_point=[{"id": f"ap-{region_id}"}],
        credential=[],
        params={},
        team=[],
        is_system=True,
        is_visible=False,
        system_code=f"{NodeMgmtSyncService.SYSTEM_TASK_PREFIX}{region_id}",
    )


def _successful_sync(config, *, config_version=None):
    return NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_SUCCESS,
        started_at=timezone.now(),
        finished_at=timezone.now(),
        detail_json={"config_version": config.version if config_version is None else config_version},
    )


def _accept_with_execution(task, execution_id):
    task.task_id = execution_id
    task.exec_status = CollectRunStatusType.RUNNING
    task.save(update_fields=["task_id", "exec_status", "updated_at"])
    return WebUtils.response_success(task.pk)


def test_collect_waits_for_first_successful_sync(config):
    with patch.object(NodeMgmtSyncService, "_list_region_collect_tasks") as collect_tasks:
        run = NodeMgmtSyncService.execute_collect(operator="system")

    assert run.status == NodeMgmtSyncRun.STATUS_WAITING_SYNC
    assert run.reason_code == "SYNC_REQUIRED"
    assert run.active_scope is None
    assert run.finished_at is None
    collect_tasks.assert_not_called()


def test_collect_waits_when_successful_sync_is_for_older_config_version(config):
    _successful_sync(config, config_version=config.version)
    config.version += 1
    config.save(update_fields=["version", "updated_at"])

    run = NodeMgmtSyncService.execute_collect(operator="system")

    assert run.status == NodeMgmtSyncRun.STATUS_WAITING_SYNC
    assert run.reason_code == "SYNC_REQUIRED"


def test_rejected_child_submission_is_blocked_not_success(config):
    _successful_sync(config)
    collect_task = _collect_task(7)

    with patch.object(
        CollectModelService, "exec_task", return_value=WebUtils.response_error({}, "任务正在执行", status_code=400),
    ):
        run = NodeMgmtSyncService.execute_collect(operator="system")

    run.refresh_from_db()
    state = run.region_states.get()
    assert run.status == NodeMgmtSyncRun.STATUS_BLOCKED
    assert run.finished_at is not None
    assert state.status == NodeMgmtSyncRun.STATUS_BLOCKED
    assert state.reason_code == "COLLECT_ALREADY_RUNNING"
    assert state.collect_task_id == collect_task.pk
    assert state.child_execution_id == ""


def test_accepted_child_makes_parent_submitted_not_success(config):
    _successful_sync(config)
    collect_task = _collect_task(7)

    with patch.object(
        CollectModelService, "exec_task", side_effect=lambda task, operator: _accept_with_execution(task, "execution-7"),
    ):
        run = NodeMgmtSyncService.execute_collect(operator="system")

    run.refresh_from_db()
    state = run.region_states.get()
    assert run.status == NodeMgmtSyncRun.STATUS_SUBMITTED
    assert run.submitted_at is not None
    assert run.finished_at is None
    assert run.active_scope == NodeMgmtSyncService.ACTIVE_SCOPE
    assert state.status == NodeMgmtSyncRun.STATUS_SUBMITTED
    assert state.child_execution_id == "execution-7"
    assert state.submitted_at is not None
    assert state.finished_at is None
    collect_task.refresh_from_db()
    assert collect_task.exec_status == CollectRunStatusType.RUNNING


@pytest.mark.parametrize(
    ("child_statuses", "expected"),
    [
        ([CollectRunStatusType.SUCCESS, CollectRunStatusType.SUCCESS], NodeMgmtSyncRun.STATUS_SUCCESS,),
        ([CollectRunStatusType.SUCCESS, CollectRunStatusType.ERROR], NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS,),
        ([CollectRunStatusType.ERROR, CollectRunStatusType.ERROR], NodeMgmtSyncRun.STATUS_FAILED,),
    ],
)
def test_parent_finishes_from_child_terminal_states(config, child_statuses, expected):
    _successful_sync(config)
    collect_tasks = [_collect_task(7), _collect_task(8)]

    def accept(task, operator):
        return _accept_with_execution(task, f"execution-{task.pk}")

    with patch.object(CollectModelService, "exec_task", side_effect=accept):
        run = NodeMgmtSyncService.execute_collect(operator="system")

    assert run.status == NodeMgmtSyncRun.STATUS_SUBMITTED
    for task, child_status in zip(collect_tasks, child_statuses):
        CollectModels.objects.filter(pk=task.pk).update(exec_status=child_status)

    refreshed = NodeMgmtSyncService.refresh_collect_run(run.pk)

    assert refreshed.status == expected
    assert refreshed.finished_at is not None
    assert refreshed.active_scope is None
    assert not refreshed.region_states.filter(status=NodeMgmtSyncRun.STATUS_SUBMITTED).exists()


def test_parent_stays_submitted_while_any_child_is_running(config):
    _successful_sync(config)
    first = _collect_task(7)
    second = _collect_task(8)

    with patch.object(
        CollectModelService, "exec_task", side_effect=lambda task, operator: _accept_with_execution(task, f"execution-{task.pk}"),
    ):
        run = NodeMgmtSyncService.execute_collect(operator="system")

    CollectModels.objects.filter(pk=first.pk).update(exec_status=CollectRunStatusType.SUCCESS)
    CollectModels.objects.filter(pk=second.pk).update(exec_status=CollectRunStatusType.RUNNING)

    refreshed = NodeMgmtSyncService.refresh_collect_run(run.pk)

    assert refreshed.status == NodeMgmtSyncRun.STATUS_SUBMITTED
    assert refreshed.finished_at is None
    assert refreshed.active_scope == NodeMgmtSyncService.ACTIVE_SCOPE
    assert refreshed.region_states.get(collect_task=first).status == "success"
    assert refreshed.region_states.get(collect_task=second).status == "submitted"


def test_periodic_collect_refreshes_submitted_runs_before_starting_next(mocker):
    from apps.cmdb.tasks.node_mgmt_sync import run_collect

    recover = mocker.patch.object(NodeMgmtSyncService, "recover_stale_runs")
    refresh = mocker.patch.object(NodeMgmtSyncService, "refresh_submitted_collect_runs")
    trigger = mocker.patch.object(NodeMgmtSyncService, "trigger_collect", return_value={"status": "submitted"},)

    assert run_collect() == {"status": "submitted"}
    recover.assert_called_once_with()
    refresh.assert_called_once_with()
    trigger.assert_called_once_with()


def test_consecutive_collect_runs_keep_independent_region_history(config):
    _successful_sync(config)
    collect_task = _collect_task(7)
    node_config_state = NodeMgmtSyncRegionState.objects.create(
        config=config,
        config_version=config.version,
        cloud_region_id="7",
        collect_task=collect_task,
        scope_key=f"config:{config.version}:region:7",
        node_config_status="healthy",
    )

    with patch.object(
        CollectModelService, "exec_task", side_effect=lambda task, operator: _accept_with_execution(task, f"execution-{operator}"),
    ):
        first = NodeMgmtSyncService.execute_collect(operator="first")
        CollectModels.objects.filter(pk=collect_task.pk).update(exec_status=CollectRunStatusType.SUCCESS)
        NodeMgmtSyncService.refresh_collect_run(first.pk)
        second = NodeMgmtSyncService.execute_collect(operator="second")

    first_state = first.region_states.get()
    second_state = second.region_states.get()
    assert first_state.pk != second_state.pk
    assert first_state.scope_key == f"collect-run:{first.pk}:region:7"
    assert second_state.scope_key == f"collect-run:{second.pk}:region:7"
    assert first_state.child_execution_id == "execution-first"
    assert second_state.child_execution_id == "execution-second"
    node_config_state.refresh_from_db()
    assert node_config_state.run_id is None
    assert node_config_state.node_config_status == "healthy"


def test_invalid_region_child_is_persisted_and_makes_mixed_result_partial(config):
    _successful_sync(config)
    invalid_task = _collect_task(7)
    invalid_task.system_code = f"{NodeMgmtSyncService.SYSTEM_TASK_PREFIX}bad"
    invalid_task.save(update_fields=["system_code", "updated_at"])
    valid_task = _collect_task(8)

    with patch.object(
        CollectModelService, "exec_task", side_effect=lambda task, operator: _accept_with_execution(task, "execution-valid"),
    ):
        run = NodeMgmtSyncService.execute_collect(operator="system")

    invalid_state = run.region_states.get(collect_task=invalid_task)
    assert invalid_state.scope_key == f"collect-run:{run.pk}:task:{invalid_task.pk}"
    assert invalid_state.status == NodeMgmtSyncRun.STATUS_BLOCKED
    assert invalid_state.reason_code == "INVALID_REGION_CODE"
    CollectModels.objects.filter(pk=valid_task.pk).update(exec_status=CollectRunStatusType.SUCCESS)

    refreshed = NodeMgmtSyncService.refresh_collect_run(run.pk)

    assert refreshed.status == NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS


def test_submission_binds_in_memory_execution_id_not_concurrently_overwritten_db_value(config):
    _successful_sync(config)
    _collect_task(7)

    def accept_then_overwrite(task, operator):
        response = _accept_with_execution(task, "execution-this-run")
        CollectModels.objects.filter(pk=task.pk).update(task_id="execution-other-run")
        return response

    with patch.object(CollectModelService, "exec_task", side_effect=accept_then_overwrite):
        run = NodeMgmtSyncService.execute_collect(operator="system")

    state = run.region_states.get()
    assert state.child_execution_id == "execution-this-run"
    refreshed = NodeMgmtSyncService.refresh_collect_run(run.pk)
    assert refreshed.status == NodeMgmtSyncRun.STATUS_FAILED
    state.refresh_from_db()
    assert state.reason_code == "COLLECT_EXECUTION_SUPERSEDED"


def test_execute_collect_forwards_operator_to_child_submission(config):
    _successful_sync(config)
    collect_task = _collect_task(7)

    def accept(task, operator):
        assert operator == "alice"
        return _accept_with_execution(task, "execution-alice")

    with patch.object(CollectModelService, "exec_task", side_effect=accept) as submit:
        run = NodeMgmtSyncService.execute_collect(operator="alice")

    assert run.status == NodeMgmtSyncRun.STATUS_SUBMITTED
    submit.assert_called_once_with(collect_task, "alice")
