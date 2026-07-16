from django.core.management.base import BaseCommand, CommandError

from apps.cmdb.services.node_mgmt_sync_reconciler import NodeMgmtSyncReconciler
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.cmdb.tasks.node_mgmt_sync import ensure_recovery_periodic_task


class Command(BaseCommand):
    help = "对账节点管理同步期望状态并恢复陈旧运行"

    def handle(self, *args, **options):
        try:
            ensure_recovery_periodic_task()
            NodeMgmtSyncService.recover_stale_runs()
            NodeMgmtSyncService.refresh_submitted_collect_runs()
            config = NodeMgmtSyncService.get_task()
            result = NodeMgmtSyncReconciler.reconcile(config, reconcile_node_configs=True,)
        except Exception:
            raise CommandError("节点管理同步恢复失败: RECOVERY_FAILED") from None

        if result.schedule_status != "healthy":
            raise CommandError("节点管理同步对账失败: RECONCILE_FAILED")
        if result.node_config_status == "degraded":
            raise CommandError("节点管理同步对账失败: NODE_CONFIG_RECONCILE_FAILED")
        self.stdout.write(self.style.SUCCESS("节点管理同步对账完成"))
