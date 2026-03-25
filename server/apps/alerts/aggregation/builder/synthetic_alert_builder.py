import re
import uuid
from typing import Any, Dict, Optional

from apps.alerts.constants import AlertStatus, AlarmStrategyType
from apps.alerts.models import Alert
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.utils.util import str_to_md5
from apps.core.logger import alert_logger as logger


class SyntheticAlertBuilder:
    @staticmethod
    def build_fingerprint(strategy_id: int) -> str:
        return str_to_md5(f"{AlarmStrategyType.MISSING_DETECTION}:{strategy_id}")

    @staticmethod
    def render_template(template: str, context: Dict[str, Any]) -> str:
        if not template:
            return ""

        def replace_var(match: re.Match[str]) -> str:
            variable_name = match.group(1).strip()
            if variable_name not in context:
                logger.debug("缺失检查模板变量缺失: variable=%s", variable_name)
            value = context.get(variable_name)
            return "" if value is None else str(value)

        return re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_var, template)

    @staticmethod
    def find_active_alert(strategy: AlarmStrategy) -> Optional[Alert]:
        fingerprint = SyntheticAlertBuilder.build_fingerprint(strategy.id)
        return (
            Alert.objects.filter(
                rule_id=str(strategy.id),
                group_by_field=AlarmStrategyType.MISSING_DETECTION,
                fingerprint=fingerprint,
                status__in=AlertStatus.ACTIVATE_STATUS,
            )
            .order_by("-updated_at")
            .first()
        )

    @staticmethod
    def create_alert(strategy: AlarmStrategy, params: Dict[str, Any], now) -> Alert:
        active_alert = SyntheticAlertBuilder.find_active_alert(strategy)
        if active_alert:
            return active_alert

        template = params.get("alert_template") or {}
        context = params.get("last_heartbeat_context") or {}
        fingerprint = SyntheticAlertBuilder.build_fingerprint(strategy.id)
        title = SyntheticAlertBuilder.render_template(
            template.get("title", ""), context
        )
        content = SyntheticAlertBuilder.render_template(
            template.get("description", ""), context
        )

        return Alert.objects.create(
            alert_id=f"ALERT-{uuid.uuid4().hex.upper()}",
            status=AlertStatus.UNASSIGNED,
            level=str(template.get("level") or "0"),
            title=title or "缺失检查告警",
            content=content,
            labels=context,
            first_event_time=now,
            last_event_time=now,
            item=context.get("item"),
            resource_id=context.get("resource_id"),
            resource_name=context.get("resource_name"),
            resource_type=context.get("resource_type"),
            fingerprint=fingerprint,
            group_by_field=AlarmStrategyType.MISSING_DETECTION,
            rule_id=str(strategy.id),
            team=strategy.dispatch_team,
        )
