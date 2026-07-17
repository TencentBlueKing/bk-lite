from celery import shared_task
from celery_singleton import Singleton
from datetime import datetime, timedelta, timezone
import time
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.constants.alert_policy import AlertConstants
from apps.log.constants.database import DatabaseConstants
from apps.log.models.policy import Alert, Event, Policy
from apps.core.logger import celery_logger as logger
from apps.log.services.alert_lifecycle_notify import LogAlertLifecycleNotifier
from apps.log.tasks.services.policy_scan import LogPolicyScan
from apps.log.tasks.utils.policy import period_to_seconds
from apps.system_mgmt.models.channel import Channel, ChannelChoices


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
    """日志告警生命周期通知补偿。

    产生事件复用 Event 的发送状态与重试次数；关闭事件复用 Alert 的状态、关闭时间与
    notice。
    两类对象均限制在补偿窗口、最小落库年龄与批量上限内，通知语义为 at-least-once。
    """
    start_time = time.time()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=AlertConstants.NOTICE_COMPENSATE_WINDOW_SECONDS)
    # 仅补偿落库已超 MIN_AGE 的事件：等待本轮扫描的同步 notice() 完成，降低与首发并发双投的概率
    # （门槛取值须大于 notice() 最坏耗时量级，见 AlertConstants 说明；通知语义为 at-least-once）
    settle_before = now - timedelta(seconds=AlertConstants.NOTICE_COMPENSATE_MIN_AGE_SECONDS)

    # closed 没有独立重试字段，仅扫描明确指向告警中心的策略。
    alert_center_channel_ids = {
        channel.id
        for channel in Channel.objects.filter(channel_type=ChannelChoices.NATS)
        if (channel.config or {}).get("method_name") == LogAlertLifecycleNotifier.ALERT_CENTER_METHOD
    }

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
        .select_related("policy", "alert")
        .order_by("event_time")[: AlertConstants.NOTICE_COMPENSATE_BATCH_SIZE]
    )

    pending_closed = list(
        Alert.objects.filter(
            status=AlertConstants.STATUS_CLOSED,
            notice=False,
            end_event_time__gte=window_start,
            end_event_time__lte=settle_before,
            policy__notice=True,
            policy__notice_type_id__in=alert_center_channel_ids,
        )
        .select_related("policy", "collect_type")
        .prefetch_related("policy__policyorganization_set")
        .order_by("end_event_time")[: AlertConstants.NOTICE_COMPENSATE_BATCH_SIZE]
    )

    if not pending and not pending_closed:
        duration = time.time() - start_time
        logger.info(f"日志通知补偿：无待补偿生命周期，耗时: {duration:.2f}s")
        return {"success": True, "scanned": 0, "compensated": 0, "duration": duration}

    scanners = {}  # 按策略复用 scanner，避免重复构造
    updated_events = []
    success_alert_ids = set()

    for event in pending:
        policy = event.policy
        # 普通渠道没有通知人时直接结束；告警中心 NATS 不依赖 notice_users。
        is_alert_center = policy.notice_type_id in alert_center_channel_ids
        if not policy.notice_users and not is_alert_center:
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
        # 状态条件防止 created 的迟到回执覆盖并发关闭留下的补偿标记。
        Alert.objects.filter(
            id__in=success_alert_ids,
            status=AlertConstants.STATUS_NEW,
        ).update(notice=True)

    closed_success_count = 0
    for alert in pending_closed:
        notifier = LogAlertLifecycleNotifier(alert.policy)
        if not notifier.is_alert_center_channel():
            continue

        success, _ = notifier.notify_closed(alert, max_attempts=1)
        if success:
            # 关闭时间参与条件更新，避免迟到回执写入新的生命周期状态。
            closed_success_count += Alert.objects.filter(
                id=alert.id,
                status=AlertConstants.STATUS_CLOSED,
                end_event_time=alert.end_event_time,
                notice=False,
            ).update(notice=True)

    duration = time.time() - start_time
    scanned_count = len(pending) + len(pending_closed)
    compensated_count = len(success_alert_ids) + closed_success_count
    logger.info(
        "日志通知补偿完成：扫描 %s 个生命周期，成功补发 %s 个，耗时: %.2fs",
        scanned_count,
        compensated_count,
        duration,
    )
    return {
        "success": True,
        "scanned": scanned_count,
        "compensated": compensated_count,
        "duration": duration,
    }
