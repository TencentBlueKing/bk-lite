# -- coding: utf-8 --
# @File: action_tasks.py

from celery import shared_task

from apps.core.logger import alert_logger as logger


@shared_task
def process_alert_actions(alert_id: str, event_name: str):
    """异步评估并分派告警动作规则。"""
    try:
        from apps.alerts.action.engine import ActionEngine
        from apps.alerts.models.models import Alert

        alert = Alert.objects.filter(alert_id=alert_id).first()
        if not alert:
            logger.warning("[ActionEngine] 告警不存在 alert=%s", alert_id)
            return
        ActionEngine().evaluate(alert, event_name)
        from apps.alerts.itsm.comments import enqueue_comment

        enqueue_comment(alert, event_name)
    except Exception:
        logger.exception("[ActionEngine] 处理动作失败 alert=%s event=%s", alert_id, event_name)
        raise
