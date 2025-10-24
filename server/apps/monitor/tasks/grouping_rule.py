from celery import shared_task

from apps.core.logger import celery_logger as logger
from apps.monitor.tasks.services.rule_group import RuleGrouping
from apps.monitor.tasks.services.sync_instance import SyncInstance


@shared_task
def sync_instance_and_group():
    """同步监控实例和分组规则"""

    logger.info("Start to update monitor instance")
    SyncInstance().run()
    logger.info("Finish to update monitor instance")

    logger.info("Start to update monitor instance grouping rule")
    RuleGrouping().update_grouping()
    logger.info("Finish to update monitor instance grouping rule")
