import logging
from django.db import IntegrityError, transaction
from apps.alerts.models.action import ActionRule, ActionExecution
from apps.alerts.action.matcher import event_matches
from apps.alerts.action.payload import build_match_payload
from apps.alerts.action.handlers.registry import get_handler
from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.utils.operator_log import record_operator_log

logger = logging.getLogger(__name__)


class ActionEngine:
    def evaluate(self, alert, event_name: str):
        """同步评估并分派（在 Celery 任务内调用）。"""
        payload = build_match_payload(alert)
        alert_teams = set(alert.team or [])
        rules = ActionRule.objects.filter(is_active=True, scope="alert")
        for rule in rules:
            if event_name not in (rule.trigger_events or []):
                continue
            rule_teams = set(rule.team or [])
            if alert_teams and rule_teams and not (alert_teams & rule_teams):
                continue
            if not event_matches(payload, rule.match_rules):
                continue
            self._dispatch(rule, alert, event_name)

    @staticmethod
    def dispatch_async(alert_id: str, event_name: str):
        """持久化动作投递意图；broker 故障时由 outbox 扫描器补投。"""
        from apps.alerts.service.outbox import enqueue_outbox

        return enqueue_outbox(
            "action",
            {"alert_id": alert_id, "event_name": event_name},
            f"action:{alert_id}:{event_name}",
        )

    def _dispatch(self, rule, alert, event_name):
        key = f"{rule.id}:{alert.alert_id}:{event_name}"
        try:
            with transaction.atomic():
                execution = ActionExecution.objects.create(
                    rule=rule, alert=alert, trigger_event=event_name, trigger_type="auto",
                    idempotency_key=key, status="pending", action_type=rule.action_type,
                )
        except IntegrityError:
            logger.info("[ActionEngine] 幂等跳过 %s", key)
            return
        try:
            record_operator_log(
                action=LogAction.EXECUTE,
                target_type=LogTargetType.ALERT,
                operator="system",
                operator_object="告警处理-动作",
                target_id=alert.alert_id,
                overview=f"规则[{rule.name}]触发动作",
            )
        except Exception:
            logger.exception("[ActionEngine] 写审计日志失败，忽略继续 key=%s", key)
        get_handler(rule.action_type).execute(rule, alert, execution)
