from celery import shared_task
from celery_singleton import Singleton
from datetime import datetime, timezone
import time

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorPolicy
from apps.core.logger import celery_logger as logger
from apps.monitor.tasks.services.policy_scan import MonitorPolicyScan
from apps.monitor.tasks.utils.policy_methods import period_to_seconds


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
        # 查询策略对象
        policy_obj = MonitorPolicy.objects.filter(id=policy_id).select_related("monitor_object").first()
        if not policy_obj:
            raise BaseAppException(f"未找到ID为 {policy_id} 的监控策略")

        # 检查策略是否启用
        if not policy_obj.enable:
            duration = time.time() - start_time
            logger.info(f"监控策略 [{policy_id}] 未启用，跳过执行，耗时: {duration:.2f}s")
            return {"success": True, "duration": duration, "message": "策略未启用"}

        # 更新最后执行时间
        current_time = datetime.now(timezone.utc)
        if not policy_obj.last_run_time:
            policy_obj.last_run_time = current_time
        else:
            # 基于上次执行时间计算下次执行时间
            next_run_time = datetime.fromtimestamp(
                policy_obj.last_run_time.timestamp() + period_to_seconds(policy_obj.period),
                tz=timezone.utc
            )
            # 如果计算的执行时间超过当前时间，使用当前时间
            policy_obj.last_run_time = min(next_run_time, current_time)

        # 只更新需要的字段，提高性能
        MonitorPolicy.objects.filter(id=policy_id).update(last_run_time=policy_obj.last_run_time)

        # 执行监控策略扫描
        logger.info(f"开始执行监控策略 [{policy_id}] 的扫描逻辑")
        MonitorPolicyScan(policy_obj).run()

        duration = time.time() - start_time
        logger.info(f"监控策略 [{policy_id}] 扫描完成，耗时: {duration:.2f}s")
        return {"success": True, "duration": duration, "message": "执行成功"}

    except BaseAppException as e:
        duration = time.time() - start_time
        logger.error(f"监控策略 [{policy_id}] 执行失败（业务异常），耗时: {duration:.2f}s，错误: {str(e)}")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"监控策略 [{policy_id}] 执行失败（系统异常），耗时: {duration:.2f}s，错误: {str(e)}",
            exc_info=True
        )
        raise
