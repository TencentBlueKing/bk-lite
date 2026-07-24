import json
from typing import Any

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncRegionState
from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.core.utils.celery_utils import CeleryUtils

RECOVERY_PERIODIC_TASK_NAME = "cmdb_node_mgmt_sync_recovery"
RECOVERY_TASK = "apps.cmdb.tasks.node_mgmt_sync.recover_node_mgmt_sync"
WATCHDOG_TASK = "apps.cmdb.tasks.node_mgmt_sync.watch_node_mgmt_sync_recovery"
RECOVERY_CRONTAB = "*/5 * * * *"
RECOVERABLE_NODE_CONFIG_STATUSES = (
    "delete_pending",
    "push_pending",
    "delete_in_progress",
    "push_in_progress",
)


def _recovery_periodic_task_matches(task) -> bool:
    if (
        task is None
        or not task.enabled
        or task.task != RECOVERY_TASK
        or task.crontab_id is None
        or task.interval_id is not None
        or task.solar_id is not None
        or task.clocked_id is not None
    ):
        return False

    minute, hour, day_of_month, month_of_year, day_of_week = RECOVERY_CRONTAB.split()
    schedule = task.crontab
    if (
        schedule.minute != minute
        or schedule.hour != hour
        or schedule.day_of_month != day_of_month
        or schedule.month_of_year != month_of_year
        or schedule.day_of_week != day_of_week
        or str(schedule.timezone) != str(timezone.get_default_timezone())
    ):
        return False

    try:
        return json.loads(task.args or "[]") == [] and json.loads(task.kwargs or "{}") == {}
    except (TypeError, ValueError):
        return False


def ensure_recovery_periodic_task():
    """保证恢复任务始终存在，不受业务自动开关控制。"""
    current = CeleryUtils.get_periodic_task(RECOVERY_PERIODIC_TASK_NAME)
    if _recovery_periodic_task_matches(current):
        return current
    return CeleryUtils.create_or_update_periodic_task(
        name=RECOVERY_PERIODIC_TASK_NAME,
        crontab=RECOVERY_CRONTAB,
        task=RECOVERY_TASK,
        enabled=True,
    )


@shared_task(name=RECOVERY_TASK)
def recover_node_mgmt_sync() -> dict[str, Any]:
    """回收陈旧运行并收敛状态，不直接发起同步或采集。"""
    ensure_recovery_periodic_task()
    recovered_runs = NodeMgmtSyncService.recover_stale_runs()
    refreshed_collect_runs = NodeMgmtSyncService.refresh_submitted_collect_runs()
    config = NodeMgmtSyncService.get_task()
    region_states = NodeMgmtSyncRegionState.objects.filter(config=config).filter(
        Q(scope_key__startswith="node-config:") | Q(scope_key__startswith="config:")
    )
    has_recoverable_region = (
        region_states.filter(
            config_version=config.version,
            node_config_status__in=RECOVERABLE_NODE_CONFIG_STATUSES,
        ).exists()
        or region_states.exclude(config_version=config.version).exists()
    )
    should_reconcile_node_configs = (
        config.node_config_status == "degraded"
        or (
            config.node_config_status == "waiting_sync"
            and config.auto_sync_enabled
            and config.auto_collect_enabled
        )
        or has_recoverable_region
    )
    result = NodeMgmtSyncReconciler.reconcile(
        config, reconcile_node_configs=should_reconcile_node_configs,
    )
    return {
        "recovered_runs": recovered_runs,
        "refreshed_collect_runs": refreshed_collect_runs,
        "schedule_status": result.schedule_status,
        "node_config_status": result.node_config_status,
    }


@shared_task(name=WATCHDOG_TASK)
def watch_node_mgmt_sync_recovery() -> None:
    """由独立静态调度修复恢复任务记录的缺失和漂移。"""
    ensure_recovery_periodic_task()


def run_sync() -> dict[str, Any]:
    NodeMgmtSyncService.recover_stale_runs()
    return NodeMgmtSyncService.trigger_sync()


def run_collect() -> dict[str, Any]:
    NodeMgmtSyncService.recover_stale_runs()
    NodeMgmtSyncService.refresh_submitted_collect_runs()
    return NodeMgmtSyncService.trigger_collect()
