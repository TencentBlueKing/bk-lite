from uuid import uuid4

from celery import shared_task
from django.core.management import call_command

from apps.core.logger import monitor_logger as logger
from apps.monitor.management.commands.patch_snmp_interface_filters import CHECKPOINT_VERSION, SnmpIfmibReconcilePartialError
from apps.monitor.services.snmp_ifmib_reconcile_state import SnmpIfmibReconcileStateService

IFMIB_RECONCILE_VERSION = CHECKPOINT_VERSION
IFMIB_RECONCILE_LOCK_TIMEOUT = 900


@shared_task
def reconcile_snmp_interface_filters():
    """运行期幂等补偿存量 IF-MIB 子配置；失败不参与 Server 启动。"""
    owner_token = uuid4().hex
    claim = SnmpIfmibReconcileStateService.claim(
        version=IFMIB_RECONCILE_VERSION,
        owner_token=owner_token,
        lease_seconds=IFMIB_RECONCILE_LOCK_TIMEOUT,
    )
    if claim.status == "completed":
        return {"status": "skipped", "reason": "already_completed"}
    if claim.status != "claimed":
        return {"status": "skipped", "reason": "already_running"}

    def persist_progress(cursor):
        renewed = SnmpIfmibReconcileStateService.renew_progress(
            version=IFMIB_RECONCILE_VERSION,
            owner_token=owner_token,
            lease_seconds=IFMIB_RECONCILE_LOCK_TIMEOUT,
            cursor=cursor,
        )
        if not renewed:
            raise RuntimeError("IF-MIB reconcile lease ownership lost")

    def compare_and_swap(node_mgmt, config_id, expected_content, content):
        result = SnmpIfmibReconcileStateService.run_owned_write(
            version=IFMIB_RECONCILE_VERSION,
            owner_token=owner_token,
            lease_seconds=IFMIB_RECONCILE_LOCK_TIMEOUT,
            write=lambda: node_mgmt.compare_and_swap_child_config_content_local(
                config_id,
                expected_content,
                content,
            ),
        )
        if not result.executed:
            raise RuntimeError("IF-MIB reconcile lease ownership lost before child write")
        return bool(result.value)

    try:
        call_command(
            "patch_snmp_interface_filters",
            batch_size=100,
            initial_cursor=claim.cursor,
            batch_completed=persist_progress,
            compare_and_swap=compare_and_swap,
            continue_on_item_error=True,
        )
        if not SnmpIfmibReconcileStateService.finish(
            version=IFMIB_RECONCILE_VERSION,
            owner_token=owner_token,
        ):
            raise RuntimeError("IF-MIB reconcile lease ownership lost before completion")
        logger.info("IF-MIB 存量子配置运行期补偿完成")
        return {"status": "completed"}
    except SnmpIfmibReconcilePartialError:
        if not SnmpIfmibReconcileStateService.reset_cursor(
            version=IFMIB_RECONCILE_VERSION,
            owner_token=owner_token,
        ):
            logger.error("IF-MIB 毒数据扫描后重置游标失败：任务已失去租约所有权")
        logger.exception("IF-MIB 存量子配置仍含无效项；健康配置已处理，将在租约过期后重新检查")
        raise
    except Exception:
        # 不释放失败租约；到期后下一次 Beat 原子接管，并从最后成功批次游标继续。
        logger.exception("IF-MIB 存量子配置运行期补偿失败，将在租约过期后从断点重试")
        raise
