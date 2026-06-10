from celery import shared_task
from celery_singleton import Singleton
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import time

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorPolicy
from apps.core.logger import celery_logger as logger
from apps.monitor.tasks.services.policy_scan import MonitorPolicyScan
from apps.monitor.tasks.utils.policy_methods import period_to_seconds
from apps.monitor.constants.alert_policy import AlertConstants


def _run_scan_and_record_success(policy_obj, scan_time):
    """Run one policy scan window and advance the watermark only after success."""
    policy_obj.last_run_time = scan_time
    MonitorPolicyScan(policy_obj).run()
    MonitorPolicy.objects.filter(id=policy_obj.id).update(last_run_time=scan_time)


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
            logger.info(f"监控策略 [{policy_id}] 首次执行，扫描时间点: {current_time}")
            _run_scan_and_record_success(policy_obj, current_time)
        else:
            period_seconds = period_to_seconds(policy_obj.period)
            gap_seconds = (current_time - policy_obj.last_run_time).total_seconds()

            gap_seconds = min(gap_seconds, AlertConstants.MAX_BACKFILL_SECONDS)

            backfill_count = int(gap_seconds // period_seconds)

            if backfill_count <= 1:
                _run_scan_and_record_success(policy_obj, current_time)
            else:
                backfill_count = min(backfill_count, AlertConstants.MAX_BACKFILL_COUNT)
                logger.info(f"监控策略 [{policy_id}] 需要补偿 {backfill_count} 个周期")

                for i in range(backfill_count):
                    scan_time = policy_obj.last_run_time + timedelta(
                        seconds=period_seconds
                    )
                    _run_scan_and_record_success(policy_obj, scan_time)
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


@shared_task(base=Singleton, raise_on_duplicate=False)
def retry_alert_center_lifecycle_notify_task():
    """补偿任务：重试推送到告警中心失败的告警通知（每5分钟执行，每次最多处理200条）"""
    from apps.monitor.models import MonitorAlert
    from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier

    alerts = list(
        MonitorAlert.objects.filter(
            status__in=["recovered", "closed"],
            alert_center_notified=False,
            alert_center_retry_count__lt=10,
        ).order_by("id")[:200]
    )
    if not alerts:
        return {"success": True, "message": "no alerts to retry"}

    logger.info(f"告警中心补偿任务：发现 {len(alerts)} 条待重试告警")

    groups = defaultdict(list)
    for alert in alerts:
        groups[alert.status].append(alert)

    notifier = AlertLifecycleNotifier()
    success_ids = []
    fail_ids = []

    for status, group_alerts in groups.items():
        results = notifier.push_to_alert_center_only(group_alerts, action=status)
        for alert, pushed_ok in results:
            if pushed_ok:
                success_ids.append(alert.id)
            else:
                fail_ids.append(alert.id)

    alerts_by_id = {a.id: a for a in alerts}

    if success_ids:
        to_mark = [alerts_by_id[aid] for aid in success_ids]
        for alert in to_mark:
            alert.alert_center_notified = True
            alert.alert_center_retry_count = 0
        MonitorAlert.objects.bulk_update(to_mark, fields=["alert_center_notified", "alert_center_retry_count"])

    if fail_ids:
        to_inc = [alerts_by_id[aid] for aid in fail_ids]
        for alert in to_inc:
            alert.alert_center_retry_count += 1
        MonitorAlert.objects.bulk_update(to_inc, fields=["alert_center_retry_count"])

    logger.info(f"告警中心补偿任务完成：成功 {len(success_ids)} 条，失败 {len(fail_ids)} 条")
    return {"success": True, "total": len(alerts), "succeeded": len(success_ids), "failed": len(fail_ids)}
