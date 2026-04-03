from celery import shared_task
from celery_singleton import Singleton
from datetime import datetime, timedelta, timezone
import time
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.constants.alert_policy import AlertConstants
from apps.log.models.policy import Policy
from apps.core.logger import celery_logger as logger
from apps.log.tasks.services.policy_scan import LogPolicyScan
from apps.log.tasks.utils.policy import period_to_seconds


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

        current_time = datetime.now(timezone.utc)
        safe_time = current_time - timedelta(seconds=AlertConstants.INGEST_DELAY_SECONDS)
        overlap_seconds = AlertConstants.WINDOW_OVERLAP_SECONDS

        if not policy_obj.last_run_time:
            policy_obj.last_run_time = safe_time
            logger.info(f"日志策略 [{policy_id}] 首次执行，设置 last_run_time: {safe_time}")
            LogPolicyScan(policy_obj, scan_time=safe_time).run()
            Policy.objects.filter(id=policy_id).update(last_run_time=safe_time)
        else:
            period_seconds = period_to_seconds(policy_obj.period)
            gap_seconds = max((safe_time - policy_obj.last_run_time).total_seconds(), 0)
            gap_seconds = min(gap_seconds, AlertConstants.MAX_BACKFILL_SECONDS)

            backfill_count = int(gap_seconds // period_seconds)

            if backfill_count <= 1:
                window_end_time = safe_time
                window_start = int(window_end_time.timestamp()) - period_seconds
                if overlap_seconds > 0:
                    window_start = max(window_start - overlap_seconds, 0)

                policy_obj.last_run_time = window_end_time
                logger.info(f"开始执行日志策略 [{policy_id}] 的扫描逻辑")
                LogPolicyScan(
                    policy_obj,
                    scan_time=window_end_time,
                    window_start=window_start,
                    window_end=int(window_end_time.timestamp()),
                ).run()
                Policy.objects.filter(id=policy_id).update(last_run_time=window_end_time)
            else:
                backfill_count = min(backfill_count, AlertConstants.MAX_BACKFILL_COUNT)
                logger.info(f"日志策略 [{policy_id}] 需要补偿 {backfill_count} 个周期")

                for i in range(backfill_count):
                    previous_success_time = policy_obj.last_run_time
                    next_scan_time = policy_obj.last_run_time + timedelta(seconds=period_seconds)
                    window_start = int(previous_success_time.timestamp())
                    if overlap_seconds > 0:
                        window_start = max(window_start - overlap_seconds, 0)

                    policy_obj.last_run_time = next_scan_time
                    logger.info(f"开始执行日志策略 [{policy_id}] 的第 {i + 1}/{backfill_count} 次补偿扫描，扫描时间点: {next_scan_time}")
                    LogPolicyScan(
                        policy_obj,
                        scan_time=next_scan_time,
                        window_start=window_start,
                        window_end=int(next_scan_time.timestamp()),
                    ).run()
                    Policy.objects.filter(id=policy_id).update(last_run_time=policy_obj.last_run_time)

        duration = time.time() - start_time
        logger.info(f"日志策略 [{policy_id}] 扫描完成，耗时: {duration:.2f}s")
        return {"success": True, "duration": duration, "message": "执行成功"}

    except BaseAppException as e:
        duration = time.time() - start_time
        logger.error(f"日志策略 [{policy_id}] 执行失败（业务异常），耗时: {duration:.2f}s，错误: {str(e)}")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"日志策略 [{policy_id}] 执行失败（系统异常），耗时: {duration:.2f}s，错误: {str(e)}", exc_info=True)
        raise
