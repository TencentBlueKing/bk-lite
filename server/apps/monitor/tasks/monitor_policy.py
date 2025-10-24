from celery.app import shared_task
from datetime import datetime, timezone
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorPolicy
from apps.core.logger import celery_logger as logger
from apps.monitor.tasks.services.policy_scan import MonitorPolicyScan
from apps.monitor.tasks.utils.policy_methods import period_to_seconds


@shared_task
def scan_policy_task(policy_id):
    """扫描监控策略"""
    logger.info(f"start to update monitor instance grouping rule, [{policy_id}]")

    policy_obj = MonitorPolicy.objects.filter(id=policy_id).select_related("monitor_object").first()
    if not policy_obj:
        raise BaseAppException(f"No MonitorPolicy found with id {policy_id}")

    if policy_obj.enable:
        if not policy_obj.last_run_time:
            policy_obj.last_run_time = datetime.now(timezone.utc)
        policy_obj.last_run_time = datetime.fromtimestamp(policy_obj.last_run_time.timestamp() + period_to_seconds(policy_obj.period), tz=timezone.utc)

        # 如果最后执行时间大于当前时间，将最后执行时间设置为当前时间
        if policy_obj.last_run_time > datetime.now(timezone.utc):
            policy_obj.last_run_time = datetime.now(timezone.utc)
        policy_obj.save()
        MonitorPolicyScan(policy_obj).run()                        # 执行监控策略

    logger.info(f"end to update monitor instance grouping rule, [{policy_id}]")
