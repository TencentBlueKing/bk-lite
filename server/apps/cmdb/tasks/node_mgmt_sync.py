from typing import Any

from celery import shared_task

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


def ensure_recovery_periodic_task():
    """保证恢复任务始终存在，不受业务自动开关控制。"""
    return CeleryUtils.create_or_update_periodic_task(name=RECOVERY_PERIODIC_TASK_NAME, crontab=RECOVERY_CRONTAB, task=RECOVERY_TASK, enabled=True,)


@shared_task(name=RECOVERY_TASK)
def recover_node_mgmt_sync() -> dict[str, Any]:
    """回收陈旧运行并收敛状态，不直接发起同步或采集。"""
    ensure_recovery_periodic_task()
    recovered_runs = NodeMgmtSyncService.recover_stale_runs()
    refreshed_collect_runs = NodeMgmtSyncService.refresh_submitted_collect_runs()
    config = NodeMgmtSyncService.get_task()
    has_recoverable_region = NodeMgmtSyncRegionState.objects.filter(
        config=config, config_version=config.version, node_config_status__in=RECOVERABLE_NODE_CONFIG_STATUSES,
    ).exists()
    result = NodeMgmtSyncReconciler.reconcile(config, reconcile_node_configs=(config.node_config_status == "degraded" or has_recoverable_region),)
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
