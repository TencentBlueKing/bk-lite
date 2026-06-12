from celery import shared_task
from celery_singleton import Singleton
from datetime import datetime, timedelta, timezone
import time
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.constants.alert_policy import AlertConstants
from apps.log.constants.database import DatabaseConstants
from apps.log.models.policy import Alert, Event, Policy
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


@shared_task(base=Singleton, raise_on_duplicate=False)
def compensate_log_notice_task():
    """日志告警通知补偿（范围B）。

    回扫近 NOTICE_COMPENSATE_WINDOW_SECONDS 内、发送未成功（notified=False）且重投未超限的事件并重发，
    兜住瞬时通道故障导致的永久漏通知。仅处理 notice 开启、策略启用、非 info 级别的事件；
    存量历史事件已在迁移中标记为 notified=True，不在补偿范围内（避免重发风暴）。
    """
    start_time = time.time()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=AlertConstants.NOTICE_COMPENSATE_WINDOW_SECONDS)
    # 仅补偿落库已超 MIN_AGE 的事件：等待本轮扫描的同步 notice() 完成，降低与首发并发双投的概率
    # （门槛取值须大于 notice() 最坏耗时量级，见 AlertConstants 说明；通知语义为 at-least-once）
    settle_before = now - timedelta(seconds=AlertConstants.NOTICE_COMPENSATE_MIN_AGE_SECONDS)

    pending = list(
        Event.objects.filter(
            notified=False,
            notice_retry_count__lt=AlertConstants.NOTICE_COMPENSATE_MAX_RETRY,
            event_time__gte=window_start,
            created_at__lte=settle_before,
            policy__notice=True,
            policy__enable=True,
        )
        .exclude(level=AlertConstants.LEVEL_INFO)
        .select_related("policy")
        .order_by("event_time")[: AlertConstants.NOTICE_COMPENSATE_BATCH_SIZE]
    )

    if not pending:
        duration = time.time() - start_time
        logger.info(f"日志通知补偿：无待补偿事件，耗时: {duration:.2f}s")
        return {"success": True, "scanned": 0, "compensated": 0, "duration": duration}

    scanners = {}  # 按策略复用 scanner，避免重复构造
    updated_events = []
    success_alert_ids = set()

    for event in pending:
        policy = event.policy
        # 无通知人 → 永远发不出，直接标记已处理避免无意义重投占用配额
        if not policy.notice_users:
            event.notified = True
            updated_events.append(event)
            continue

        scanner = scanners.get(policy.id)
        if scanner is None:
            scanner = LogPolicyScan(policy)
            scanners[policy.id] = scanner

        # 单次发送：补偿任务的周期回扫本身即外层重试，避免在 worker 内叠加内联 sleep 阻塞
        is_notice, notice_result = scanner.send_notice(event, max_attempts=1)
        event.notice_result = notice_result
        event.notified = is_notice
        event.notice_retry_count = (event.notice_retry_count or 0) + 1
        updated_events.append(event)
        if is_notice:
            success_alert_ids.add(event.alert_id)

    if updated_events:
        Event.objects.bulk_update(
            updated_events,
            ["notice_result", "notified", "notice_retry_count"],
            batch_size=DatabaseConstants.DEFAULT_BATCH_SIZE,
        )

    if success_alert_ids:
        Alert.objects.bulk_update(
            [Alert(id=alert_id, notice=True) for alert_id in success_alert_ids],
            ["notice"],
            batch_size=DatabaseConstants.DEFAULT_BATCH_SIZE,
        )

    duration = time.time() - start_time
    logger.info(f"日志通知补偿完成：扫描 {len(pending)} 个事件，成功补发 {len(success_alert_ids)} 个告警，耗时: {duration:.2f}s")
    return {"success": True, "scanned": len(pending), "compensated": len(success_alert_ids), "duration": duration}
