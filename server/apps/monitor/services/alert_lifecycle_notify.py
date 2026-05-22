from collections import defaultdict

from apps.core.logger import monitor_logger as logger
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils
from apps.system_mgmt.models import Channel


ACTION_TO_ALERT_CENTER = {
    "created": "created",
    "upgraded": "updated",
    "recovered": "recovery",
    "closed": "closed",
}

LEVEL_TO_ALERT_CENTER = {
    "critical": "0",
    "error": "1",
    "warning": "2",
    "info": "3",
    "no_data": "2",
}


class AlertLifecycleNotifier:
    def __init__(self, policy=None):
        self.policy = policy

    def notify_alerts(self, alerts, action, operator="", reason=""):
        if not alerts:
            return

        groups = defaultdict(list)
        for alert in alerts:
            channel_ids = self._resolve_notice_type_ids(alert)
            notice_users = self._resolve_notice_users(alert)
            if not channel_ids:
                logger.warning(f"Alert {alert.id} has no notice_type_ids configured, skip notification")
                continue
            for channel_id in channel_ids:
                groups[(channel_id, tuple(notice_users) if notice_users else ())].append(alert)

        for (channel_id, notice_users_tuple), group_alerts in groups.items():
            notice_users = list(notice_users_tuple)
            try:
                self._send_to_channel(channel_id, notice_users, group_alerts, action, operator, reason)
            except Exception as e:
                logger.error(
                    f"Lifecycle notify exception: action={action}, channel_id={channel_id}, error={e}",
                    exc_info=True,
                )

    def _resolve_notice_type_ids(self, alert):
        if alert.notice_type_ids:
            return alert.notice_type_ids
        if self.policy and self.policy.notice and self.policy.notice_type_ids:
            return self.policy.notice_type_ids
        return []

    def _resolve_notice_users(self, alert):
        if alert.notice_users:
            return alert.notice_users
        if self.policy and self.policy.notice_users:
            return self.policy.notice_users
        return []

    def _send_to_channel(self, channel_id, notice_users, alerts, action, operator, reason):
        channel = Channel.objects.filter(id=channel_id).first()
        if not channel:
            logger.warning(f"Channel {channel_id} not found, skip notification for {len(alerts)} alerts")
            return

        is_alert_center = channel.channel_type == "nats" and channel.config.get("method_name") == "receive_alert_events"

        if is_alert_center:
            self._push_to_alert_center(channel_id, alerts, action, operator, reason)
        else:
            self._send_normal_notice(channel_id, notice_users, alerts, action, operator, reason)

    def _send_normal_notice(self, channel_id, notice_users, alerts, action, operator, reason):
        for alert in alerts:
            title = self._build_title(alert, action)
            content = self._build_content(alert, action, operator, reason)
            try:
                send_result = SystemMgmtUtils.send_msg_with_channel(channel_id, title, content, notice_users)
                if send_result.get("result") is False:
                    logger.error(f"Normal notify failed: alert={alert.id}, action={action}, message={send_result.get('message', 'Unknown error')}")
                else:
                    logger.info(f"Normal notify success: alert={alert.id}, action={action}")
            except Exception as e:
                logger.error(f"Normal notify exception: alert={alert.id}, action={action}, error={e}", exc_info=True)

    def _push_to_alert_center(self, channel_id, alerts, action, operator, reason):
        content = {
            "source_id": "nats",
            "pusher": "lite-monitor",
            "events": [self._build_alert_center_payload(alert, action, operator, reason) for alert in alerts],
        }
        try:
            send_result = SystemMgmtUtils.send_msg_with_channel(channel_id, "", content, [])
            if send_result.get("result") is False:
                logger.error(
                    f"Lifecycle push to alert center failed: action={action}, "
                    f"count={len(alerts)}, message={send_result.get('message', 'Unknown error')}"
                )
            else:
                logger.info(f"Lifecycle push to alert center success: action={action}, count={len(alerts)}")
        except Exception as e:
            logger.error(f"Lifecycle push to alert center exception: action={action}, error={e}", exc_info=True)

    def _build_alert_center_payload(self, alert, action, operator, reason):
        alert_center_action = ACTION_TO_ALERT_CENTER.get(action, "created")
        start_time = str(int(alert.start_event_time.timestamp())) if alert.start_event_time else None
        end_time = str(int(alert.end_event_time.timestamp())) if alert.end_event_time else None
        return {
            "external_id": str(alert.id),
            "rule_id": str(alert.policy_id),
            "title": alert.content,
            "description": alert.content,
            "level": LEVEL_TO_ALERT_CENTER.get(alert.level, "3"),
            "value": float(alert.value) if alert.value is not None else None,
            "action": alert_center_action,
            "start_time": start_time,
            "end_time": end_time,
            "resource_id": alert.monitor_instance_id,
            "resource_name": getattr(alert, "monitor_instance_name", ""),
            "tags": getattr(alert, "dimensions", {}),
            "labels": {
                "policy_name": getattr(self.policy, "name", "") if self.policy else "",
                "metric_instance_id": getattr(alert, "metric_instance_id", ""),
                "operator": operator,
                "reason": reason,
                "status": alert.status,
            },
        }

    def _build_title(self, alert, action):
        action_labels = {
            "created": "告警产生",
            "upgraded": "告警升级",
            "closed": "告警关闭",
            "recovered": "告警恢复",
        }
        label = action_labels.get(action, "告警通知")
        policy_name = getattr(self.policy, "name", "") if self.policy else ""
        return f"{label}：{policy_name}" if policy_name else label

    def _build_content(self, alert, action, operator, reason):
        parts = [f"告警内容：{alert.content}"]

        instance_name = getattr(alert, "monitor_instance_name", "") or alert.monitor_instance_id
        if instance_name:
            parts.append(f"资源：{instance_name}")

        parts.append(f"级别：{alert.level}")

        if action == "upgraded":
            parts.append("状态：告警级别已升级")
        elif action == "closed":
            if operator:
                parts.append(f"操作人：{operator}")
            if reason:
                parts.append(f"原因：{reason}")
        elif action == "recovered":
            parts.append("状态：已自动恢复")

        if alert.start_event_time:
            parts.append(f"开始时间：{alert.start_event_time.strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(parts)
