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
            # 启动阶段（migrate -> init -> 起 server/NATS listener）远端响应方必然
            # 未就绪，这里只做本地 DB 对账；节点配置的远端交付由周期恢复任务
            # recover_node_mgmt_sync 在服务起来后收敛，交付失败不阻断启动。
            result = NodeMgmtSyncReconciler.reconcile(config)
        except Exception:
            raise CommandError("节点管理同步恢复失败: RECOVERY_FAILED") from None

        if result.schedule_status != "healthy":
            raise CommandError("节点管理同步对账失败: RECONCILE_FAILED")
        self.stdout.write(self.style.SUCCESS("节点管理同步对账完成"))
