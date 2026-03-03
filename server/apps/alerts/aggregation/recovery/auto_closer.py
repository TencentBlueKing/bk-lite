from apps.alerts.models.models import Alert
from apps.alerts.constants.constants import AlertStatus
from apps.core.logger import alert_logger as logger


class AutoCloser:
    @staticmethod
    def handle_closed_events(events_queryset):
        from apps.alerts.constants.constants import EventAction

        closed_events = events_queryset.filter(action=EventAction.CLOSED)

        for event in closed_events:
            external_id = event.external_id
            if not external_id:
                continue

            matching_alerts = Alert.objects.filter(
                status__in=AlertStatus.ACTIVATE_STATUS,
                events__external_id=external_id,
            ).distinct()

            for alert in matching_alerts:
                AutoCloser._close_alert(alert)

    @staticmethod
    def _close_alert(alert: Alert):
        alert.status = AlertStatus.AUTO_CLOSE
        alert.save(update_fields=["status", "updated_at"])
        logger.info(f"自动关闭告警: {alert.alert_id}")
