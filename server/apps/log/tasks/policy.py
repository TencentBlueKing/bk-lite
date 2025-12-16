from celery import shared_task
from celery_singleton import Singleton
from datetime import datetime, timezone
import time
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.models.policy import Policy
from apps.core.logger import celery_logger as logger
from apps.log.tasks.services.policy_scan import LogPolicyScan


@shared_task(base=Singleton, raise_on_duplicate=False)
def scan_log_policy_task(policy_id):
    """扫描日志策略

    Args:
        policy_id: 日志策略ID

    Returns:
        dict: 执行结果 {"success": bool, "duration": float, "message": str}
    """
    start_time = time.time()
    logger.info(f"开始执行日志策略扫描任务，策略ID: {policy_id}")

    try:
        # 查询策略对象
        policy_obj = Policy.objects.filter(id=policy_id).select_related("collect_type").first()
        if not policy_obj:
            raise BaseAppException(f"未找到ID为 {policy_id} 的日志策略")

        # 检查策略是否启用
        if not policy_obj.enable:
            duration = time.time() - start_time
            logger.info(f"日志策略 [{policy_id}] 未启用，跳过执行，耗时: {duration:.2f}s")
            return {"success": True, "duration": duration, "message": "策略未启用"}

        # 更新最后执行时间为当前时间（日志策略使用当前时间作为扫描时间点）
        current_time = datetime.now(timezone.utc)
        policy_obj.last_run_time = current_time

        # 只更新需要的字段，提高性能
        Policy.objects.filter(id=policy_id).update(last_run_time=policy_obj.last_run_time)

        # 执行日志策略扫描
        logger.info(f"开始执行日志策略 [{policy_id}] 的扫描逻辑")
        LogPolicyScan(policy_obj).run()

        duration = time.time() - start_time
        logger.info(f"日志策略 [{policy_id}] 扫描完成，耗时: {duration:.2f}s")
        return {"success": True, "duration": duration, "message": "执行成功"}

    except BaseAppException as e:
        duration = time.time() - start_time
        logger.error(f"日志策略 [{policy_id}] 执行失败（业务异常），耗时: {duration:.2f}s，错误: {str(e)}")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"日志策略 [{policy_id}] 执行失败（系统异常），耗时: {duration:.2f}s，错误: {str(e)}",
            exc_info=True
        )
        raise
