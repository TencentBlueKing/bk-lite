import logging
from django.db import IntegrityError, transaction
from apps.alerts.models.action import ActionRule, ActionExecution
from apps.alerts.action.matcher import event_matches
from apps.alerts.action.payload import build_match_payload
from apps.alerts.action.handlers.registry import get_handler

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
        get_handler(rule.action_type).execute(rule, alert, execution)
