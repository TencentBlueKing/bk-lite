from celery import shared_task
from celery_singleton import Singleton
from datetime import datetime, timedelta, timezone
import time

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorPolicy
from apps.core.logger import celery_logger as logger
from apps.monitor.tasks.services.policy_scan import MonitorPolicyScan
from apps.monitor.tasks.utils.policy_methods import period_to_seconds
from apps.monitor.constants.alert_policy import AlertConstants


@shared_task(base=Singleton, raise_on_duplicate=False)
def scan_policy_task(policy_id):
    """扫描监控策略

    Args:
        policy_id: 监控策略ID

    Returns:
        dict: 执行结果 {"success": bool, "duration": float, "message": str}
    """
    start_time = time.time()
    logger.info(f"开始执行监控策略扫描任务，策略ID: {policy_id}")

    try:
        policy_obj = (
            MonitorPolicy.objects.filter(id=policy_id)
            .select_related("monitor_object")
            .first()
        )
        if not policy_obj:
            raise BaseAppException(f"未找到ID为 {policy_id} 的监控策略")

        if not policy_obj.enable:
            duration = time.time() - start_time
            logger.info(
                f"监控策略 [{policy_id}] 未启用，跳过执行，耗时: {duration:.2f}s"
            )
            return {"success": True, "duration": duration, "message": "策略未启用"}

        current_time = datetime.now(timezone.utc)

        if not policy_obj.last_run_time:
            policy_obj.last_run_time = current_time
            MonitorPolicy.objects.filter(id=policy_id).update(
                last_run_time=current_time
            )
            logger.info(
                f"监控策略 [{policy_id}] 首次执行，设置 last_run_time: {current_time}"
            )
            MonitorPolicyScan(policy_obj).run()
        else:
            period_seconds = period_to_seconds(policy_obj.period)
            gap_seconds = (current_time - policy_obj.last_run_time).total_seconds()

            gap_seconds = min(gap_seconds, AlertConstants.MAX_BACKFILL_SECONDS)

            backfill_count = int(gap_seconds // period_seconds)

            if backfill_count <= 1:
                policy_obj.last_run_time = current_time
                MonitorPolicy.objects.filter(id=policy_id).update(
                    last_run_time=current_time
                )
                MonitorPolicyScan(policy_obj).run()
            else:
                backfill_count = min(backfill_count, AlertConstants.MAX_BACKFILL_COUNT)
                logger.info(f"监控策略 [{policy_id}] 需要补偿 {backfill_count} 个周期")

                for i in range(backfill_count):
                    policy_obj.last_run_time = policy_obj.last_run_time + timedelta(
                        seconds=period_seconds
                    )
                    MonitorPolicyScan(policy_obj).run()
                    MonitorPolicy.objects.filter(id=policy_id).update(
                        last_run_time=policy_obj.last_run_time
                    )
                    logger.debug(
                        f"监控策略 [{policy_id}] 完成第 {i + 1}/{backfill_count} 次补偿"
                    )

        duration = time.time() - start_time
        logger.info(f"监控策略 [{policy_id}] 扫描完成，耗时: {duration:.2f}s")
        return {"success": True, "duration": duration, "message": "执行成功"}

    except BaseAppException as e:
        duration = time.time() - start_time
        logger.error(
            f"监控策略 [{policy_id}] 执行失败（业务异常），耗时: {duration:.2f}s，错误: {str(e)}"
        )
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"监控策略 [{policy_id}] 执行失败（系统异常），耗时: {duration:.2f}s，错误: {str(e)}",
            exc_info=True,
        )
        raise
