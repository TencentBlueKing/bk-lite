from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncRegionState, NodeMgmtSyncRun
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.cmdb.tasks.node_mgmt_sync import (
    RECOVERY_PERIODIC_TASK_NAME,
    RECOVERY_TASK,
    WATCHDOG_TASK,
    recover_node_mgmt_sync,
    watch_node_mgmt_sync_recovery,
)

pytestmark = pytest.mark.django_db

COMMAND = "apps.cmdb.management.commands.reconcile_node_mgmt_sync"


def _healthy_result():
    return SimpleNamespace(schedule_status="healthy", node_config_status="healthy", error_code="",)


def test_management_command_recovers_and_reconciles_node_configs(mocker):
    config = NodeMgmtSyncService.get_task()
    mocker.patch(f"{COMMAND}.NodeMgmtSyncService.get_task", return_value=config)
    recover = mocker.patch(f"{COMMAND}.NodeMgmtSyncService.recover_stale_runs")
    refresh = mocker.patch(f"{COMMAND}.NodeMgmtSyncService.refresh_submitted_collect_runs")
    reconcile = mocker.patch(f"{COMMAND}.NodeMgmtSyncReconciler.reconcile", return_value=_healthy_result())

    call_command("reconcile_node_mgmt_sync")

    recover.assert_called_once_with()
    refresh.assert_called_once_with()
    reconcile.assert_called_once_with(config, reconcile_node_configs=True)


def test_management_command_creates_fixed_recovery_schedule_independent_of_switches():
    config = NodeMgmtSyncService.get_task()
    config.auto_sync_enabled = False
    config.auto_collect_enabled = False
    config.save(update_fields=["auto_sync_enabled", "auto_collect_enabled", "updated_at"])

    call_command("reconcile_node_mgmt_sync")

    task = PeriodicTask.objects.get(name=RECOVERY_PERIODIC_TASK_NAME)
    assert task.task == RECOVERY_TASK
    assert task.enabled is True
    assert task.interval_id is None
    assert task.crontab.minute == "*/5"


def test_management_command_is_idempotent_and_repairs_recovery_schedule_drift():
    call_command("reconcile_node_mgmt_sync")
    task = PeriodicTask.objects.get(name=RECOVERY_PERIODIC_TASK_NAME)
    wrong_crontab = CrontabSchedule.objects.create(minute="*/1", hour="*", day_of_week="*", day_of_month="*", month_of_year="*",)
    task.task = "wrong.task"
    task.enabled = False
    task.crontab = wrong_crontab
    task.save(update_fields=["task", "enabled", "crontab"])

    call_command("reconcile_node_mgmt_sync")

    assert PeriodicTask.objects.filter(name=RECOVERY_PERIODIC_TASK_NAME).count() == 1
    task.refresh_from_db()
    assert task.task == RECOVERY_TASK
    assert task.enabled is True
    assert task.crontab.minute == "*/5"


@pytest.mark.parametrize("drift", ["deleted", "disabled", "wrong_task"])
def test_independent_watchdog_repairs_runtime_recovery_task_drift_without_command(drift,):
    call_command("reconcile_node_mgmt_sync")
    task = PeriodicTask.objects.get(name=RECOVERY_PERIODIC_TASK_NAME)
    if drift == "deleted":
        task.delete()
    elif drift == "disabled":
        task.enabled = False
        task.save(update_fields=["enabled"])
    else:
        task.task = "wrong.task"
        task.save(update_fields=["task"])

    watch_node_mgmt_sync_recovery()

    task = PeriodicTask.objects.get(name=RECOVERY_PERIODIC_TASK_NAME)
    assert task.task == RECOVERY_TASK
    assert task.enabled is True
    assert task.crontab.minute == "*/5"


def test_static_beat_schedule_runs_independent_watchdog_every_five_minutes():
    from apps.cmdb.config import CELERY_BEAT_SCHEDULE

    schedule = CELERY_BEAT_SCHEDULE["node_mgmt_sync_recovery_watchdog"]
    assert schedule["task"] == WATCHDOG_TASK
    assert schedule["schedule"]._orig_minute == "*/5"


def test_management_command_failure_is_stable_and_hides_exception_detail(mocker):
    mocker.patch(
        f"{COMMAND}.NodeMgmtSyncService.recover_stale_runs", side_effect=RuntimeError("credential=secret"),
    )

    with pytest.raises(CommandError, match="RECOVERY_FAILED") as exc_info:
        call_command("reconcile_node_mgmt_sync")

    assert "credential=secret" not in str(exc_info.value)


def test_runtime_recovery_only_repairs_health_and_degraded_node_config(mocker):
    config = NodeMgmtSyncService.get_task()
    config.node_config_status = "degraded"
    config.save(update_fields=["node_config_status", "updated_at"])
    recover = mocker.patch.object(NodeMgmtSyncService, "recover_stale_runs")
    refresh = mocker.patch.object(NodeMgmtSyncService, "refresh_submitted_collect_runs")
    reconcile = mocker.patch("apps.cmdb.services.node_mgmt_sync_reconciler.NodeMgmtSyncReconciler.reconcile", return_value=_healthy_result(),)
    trigger_sync = mocker.patch.object(NodeMgmtSyncService, "trigger_sync")
    trigger_collect = mocker.patch.object(NodeMgmtSyncService, "trigger_collect")
    ensure = mocker.patch("apps.cmdb.tasks.node_mgmt_sync.ensure_recovery_periodic_task")

    result = recover_node_mgmt_sync()

    assert result == {
        "recovered_runs": recover.return_value,
        "refreshed_collect_runs": refresh.return_value,
        "schedule_status": "healthy",
        "node_config_status": "healthy",
    }
    reconcile.assert_called_once_with(config, reconcile_node_configs=True)
    ensure.assert_called_once_with()
    trigger_sync.assert_not_called()
    trigger_collect.assert_not_called()


def test_runtime_recovery_does_not_repush_healthy_node_config(mocker):
    config = NodeMgmtSyncService.get_task()
    config.node_config_status = "healthy"
    config.save(update_fields=["node_config_status", "updated_at"])
    mocker.patch.object(NodeMgmtSyncService, "recover_stale_runs", return_value=0)
    mocker.patch.object(NodeMgmtSyncService, "refresh_submitted_collect_runs", return_value=0)
    reconcile = mocker.patch("apps.cmdb.services.node_mgmt_sync_reconciler.NodeMgmtSyncReconciler.reconcile", return_value=_healthy_result(),)

    recover_node_mgmt_sync()

    reconcile.assert_called_once_with(config, reconcile_node_configs=False)


def test_runtime_recovery_reconciles_waiting_sync_after_sync_reenabled(mocker):
    config = NodeMgmtSyncService.get_task()
    config.auto_sync_enabled = True
    config.auto_collect_enabled = True
    config.node_config_status = "waiting_sync"
    config.save(
        update_fields=[
            "auto_sync_enabled", "auto_collect_enabled", "node_config_status", "updated_at",
        ]
    )
    mocker.patch.object(NodeMgmtSyncService, "recover_stale_runs", return_value=0)
    mocker.patch.object(NodeMgmtSyncService, "refresh_submitted_collect_runs", return_value=0)
    reconcile = mocker.patch(
        "apps.cmdb.services.node_mgmt_sync_reconciler.NodeMgmtSyncReconciler.reconcile",
        return_value=_healthy_result(),
    )

    recover_node_mgmt_sync()

    reconcile.assert_called_once_with(config, reconcile_node_configs=True)


def test_runtime_recovery_reconciles_region_owned_by_older_config_version(mocker):
    config = NodeMgmtSyncService.get_task()
    config.version = 2
    config.auto_collect_enabled = False
    config.node_config_status = "healthy"
    config.save(update_fields=["version", "auto_collect_enabled", "node_config_status", "updated_at"])
    NodeMgmtSyncRegionState.objects.create(
        config=config,
        config_version=1,
        cloud_region_id="7",
        scope_key="node-config:region:7",
        node_config_status="healthy",
    )
    mocker.patch.object(NodeMgmtSyncService, "recover_stale_runs", return_value=0)
    mocker.patch.object(NodeMgmtSyncService, "refresh_submitted_collect_runs", return_value=0)
    reconcile = mocker.patch(
        "apps.cmdb.services.node_mgmt_sync_reconciler.NodeMgmtSyncReconciler.reconcile",
        return_value=_healthy_result(),
    )

    recover_node_mgmt_sync()

    reconcile.assert_called_once_with(config, reconcile_node_configs=True)


def test_runtime_recovery_ignores_old_collect_run_region_history(mocker):
    config = NodeMgmtSyncService.get_task()
    config.version = 2
    config.node_config_status = "healthy"
    config.save(update_fields=["version", "node_config_status", "updated_at"])
    run = NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
        status=NodeMgmtSyncRun.STATUS_SUCCESS,
    )
    NodeMgmtSyncRegionState.objects.create(
        config=config,
        run=run,
        config_version=1,
        cloud_region_id="7",
        scope_key=f"collect-run:{run.pk}:region:7",
        status="success",
    )
    mocker.patch.object(NodeMgmtSyncService, "recover_stale_runs", return_value=0)
    mocker.patch.object(NodeMgmtSyncService, "refresh_submitted_collect_runs", return_value=0)
    reconcile = mocker.patch(
        "apps.cmdb.services.node_mgmt_sync_reconciler.NodeMgmtSyncReconciler.reconcile",
        return_value=_healthy_result(),
    )

    recover_node_mgmt_sync()

    reconcile.assert_called_once_with(config, reconcile_node_configs=False)


@pytest.mark.parametrize("region_status", ["delete_pending", "push_pending", "delete_in_progress"])
def test_runtime_recovery_checks_current_version_recoverable_region_even_when_global_healthy(
    mocker, region_status,
):
    config = NodeMgmtSyncService.get_task()
    config.node_config_status = "healthy"
    config.save(update_fields=["node_config_status", "updated_at"])
    NodeMgmtSyncRegionState.objects.create(
        config=config,
        config_version=config.version,
        cloud_region_id="7",
        scope_key=f"config:{config.version}:region:7",
        node_config_status=region_status,
        reason_code=("NODE_CONFIG_CLAIM:crashed-owner" if region_status.endswith("_in_progress") else ""),
    )
    mocker.patch.object(NodeMgmtSyncService, "recover_stale_runs", return_value=0)
    mocker.patch.object(NodeMgmtSyncService, "refresh_submitted_collect_runs", return_value=0)
    reconcile = mocker.patch("apps.cmdb.services.node_mgmt_sync_reconciler.NodeMgmtSyncReconciler.reconcile", return_value=_healthy_result(),)

    recover_node_mgmt_sync()

    reconcile.assert_called_once_with(config, reconcile_node_configs=True)
