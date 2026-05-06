from apps.core.logger import monitor_logger as logger
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils
from apps.system_mgmt.models import Channel


class AlertLifecycleNotifier:
    def __init__(self, policy):
        self.policy = policy
        self._is_alert_center = self._check_alert_center_channel()

    def notify_alerts(self, alerts, action, operator="", reason=""):
        if not alerts or not self._should_notify() or not self._is_alert_center:
            logger.warning(f"Lifecycle notify skipped for policy {self.policy.id}: should_notify={self._should_notify()}, is_alert_center={self._is_alert_center}")
            return

        try:
            logger.info("Lifecycle alert notify")
            self._push_to_alert_center(alerts, action, operator, reason)
        except Exception as e:
            logger.error(
                f"Lifecycle notify exception for policy {self.policy.id}: action={action}, error={e}",
                exc_info=True,
            )

    def _should_notify(self):
        return bool(self.policy.notice and self.policy.notice_type_id)

    def _check_alert_center_channel(self):
        channel = Channel.objects.filter(id=self.policy.notice_type_id).first()
        if not channel:
            return False
        return channel.channel_type == "nats" and channel.config.get("method_name") == "receive_alert_events"

    def _push_to_alert_center(self, alerts, action, operator, reason):
        content = {
            "source_id": "nats",
            "pusher": "lite-monitor",
            "events": [self._build_alert_center_payload(alert, action, operator, reason) for alert in alerts],
        }
        send_result = SystemMgmtUtils.send_msg_with_channel(self.policy.notice_type_id, "", content, [])
        if send_result.get("result") is False:
            logger.error(
                f"Lifecycle push to alert center failed for policy {self.policy.id}: "
                f"action={action}, message={send_result.get('message', 'Unknown error')}"
            )
        else:
            logger.info(f"Lifecycle push to alert center success for policy {self.policy.id}: action={action}, count={len(alerts)}")

    def _build_alert_center_payload(self, alert, action, operator, reason):
        alert_center_action = self._map_action_to_alert_center(action)
        start_time = str(int(alert.start_event_time.timestamp())) if alert.start_event_time else None
        end_time = str(int(alert.end_event_time.timestamp())) if alert.end_event_time else None
        return {
            "external_id": str(alert.id),
            "rule_id": str(alert.policy_id),
            "title": alert.content,
            "description": alert.content,
            "level": self._map_level_to_alert_center(alert.level),
            "value": float(alert.value) if alert.value is not None else None,
            "action": alert_center_action,
            "start_time": start_time,
            "end_time": end_time,
            "resource_id": alert.monitor_instance_id,
            "resource_name": alert.monitor_instance_name,
            "tags": alert.dimensions,
            "labels": {
                "policy_name": self.policy.name,
                "metric_instance_id": alert.metric_instance_id,
                "operator": operator,
                "reason": reason,
                "status": alert.status,
            },
        }

    def _map_level_to_alert_center(self, level):
        level_map = {
            "critical": "0",
            "error": "1",
            "warning": "2",
            "info": "3",
            "no_data": "2",
        }
        return level_map.get(level, "3")

    def _map_action_to_alert_center(self, action):
        action_map = {
            "recovered": "recovery",
            "closed": "closed",
        }
        return action_map.get(action, "created")
