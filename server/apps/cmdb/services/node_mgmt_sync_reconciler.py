from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from apps.core.logger import cmdb_logger as logger
from apps.core.utils.celery_utils import CeleryUtils


@dataclass(frozen=True)
class NodeMgmtSyncReconcileResult:
    schedule_status: str
    node_config_status: str
    error_code: str = ""
    error_message: str = ""


class NodeMgmtSyncReconciler:
    @classmethod
    def reconcile(cls, config, *, reconcile_node_configs: bool = False):
        try:
            from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

            cls._reconcile_periodic_task(
                enabled=config.auto_sync_enabled,
                name=NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME,
                task=NodeMgmtSyncService.SYNC_TASK,
                interval=config.sync_interval_minutes,
            )
            cls._reconcile_periodic_task(
                enabled=config.auto_collect_enabled,
                name=NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME,
                task=NodeMgmtSyncService.COLLECT_TASK,
                interval=config.collect_interval_minutes,
            )
            node_status = config.node_config_status or "unknown"
            if reconcile_node_configs:
                NodeMgmtSyncService._sync_collect_node_configs(enabled=config.auto_collect_enabled)
                node_status = "healthy"
            result = NodeMgmtSyncReconcileResult("healthy", node_status)
        except Exception as exc:
            logger.error("节点管理同步对账失败: %s", type(exc).__name__)
            result = NodeMgmtSyncReconcileResult("degraded", "degraded", "RECONCILE_FAILED", f"{type(exc).__name__}: 节点管理同步对账失败",)
        cls._persist_health(config, result)
        return result

    @classmethod
    def _reconcile_periodic_task(cls, *, enabled: bool, name: str, task: str, interval: int) -> None:
        current = CeleryUtils.get_periodic_task(name)
        if not enabled:
            if current is not None:
                CeleryUtils.delete_periodic_task(name)
            return

        expected_crontab = f"*/{int(interval)} * * * *"
        if cls._matches(current, task=task, crontab=expected_crontab):
            return
        CeleryUtils.create_or_update_periodic_task(
            name=name, crontab=expected_crontab, task=task, enabled=True,
        )

    @staticmethod
    def _matches(current, *, task: str, crontab: str) -> bool:
        if current is None or current.task != task or not current.enabled:
            return False
        if current.crontab_id is None or current.interval_id is not None:
            return False
        expected = crontab.split()
        actual = [
            current.crontab.minute,
            current.crontab.hour,
            current.crontab.day_of_month,
            current.crontab.month_of_year,
            current.crontab.day_of_week,
        ]
        return actual == expected

    @staticmethod
    def _persist_health(config, result: NodeMgmtSyncReconcileResult) -> None:
        reconciled_at = timezone.now()
        config.__class__.objects.filter(pk=config.pk).update(
            schedule_status=result.schedule_status,
            node_config_status=result.node_config_status,
            last_reconciled_at=reconciled_at,
            reconcile_error_code=result.error_code,
            reconcile_error_message=result.error_message[:255],
        )
        config.schedule_status = result.schedule_status
        config.node_config_status = result.node_config_status
        config.last_reconciled_at = reconciled_at
        config.reconcile_error_code = result.error_code
        config.reconcile_error_message = result.error_message[:255]
