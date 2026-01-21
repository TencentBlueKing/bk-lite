"""事件告警管理服务 - 负责事件和告警的创建、通知"""

import uuid

from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import MonitorAlert, MonitorEvent, MonitorEventRawData
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils
from apps.core.logger import celery_logger as logger


class EventAlertManager:
    """事件告警管理服务"""

    def __init__(self, policy, instances_map: dict, active_alerts):
        self.policy = policy
        self.instances_map = instances_map
        self.active_alerts = active_alerts

    def create_events(self, events):
        """创建事件 - 支持关联告警外键"""
        if not events:
            return []

        create_events = []
        events_with_raw_data = []

        for event in events:
            event_id = uuid.uuid4().hex
            alert_id = event.get("alert_id")

            create_events.append(
                MonitorEvent(
                    id=event_id,
                    alert_id=alert_id,
                    policy_id=self.policy.id,
                    monitor_instance_id=event["instance_id"],
                    value=event["value"],
                    level=event["level"],
                    content=event["content"],
                    notice_result=True,
                    event_time=self.policy.last_run_time,
                )
            )
            if event.get("raw_data"):
                events_with_raw_data.append(
                    {"event_id": event_id, "raw_data": event["raw_data"]}
                )

        event_objs = MonitorEvent.objects.bulk_create(
            create_events, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE
        )

        if not event_objs or not hasattr(event_objs[0], "id"):
            event_objs = list(
                MonitorEvent.objects.filter(
                    policy_id=self.policy.id, event_time=self.policy.last_run_time
                ).order_by("-created_at")[: len(create_events)]
            )

        if events_with_raw_data:
            self._create_raw_data_records(events_with_raw_data, event_objs)

        return event_objs

    def _create_raw_data_records(self, events_with_raw_data, event_objs):
        """创建事件原始数据记录"""
        event_obj_map = {obj.id: obj for obj in event_objs}

        raw_data_objects = []
        for event_info in events_with_raw_data:
            event_id = event_info["event_id"]
            if (
                event_id in event_obj_map
                or MonitorEvent.objects.filter(id=event_id).exists()
            ):
                raw_data_objects.append(
                    MonitorEventRawData(event_id=event_id, data=event_info["raw_data"])
                )

        if raw_data_objects:
            for raw_data_obj in raw_data_objects:
                raw_data_obj.save()
            logger.info(
                f"Created {len(raw_data_objects)} raw data records for policy {self.policy.id}"
            )

    def create_events_and_alerts(self, events):
        """创建事件和告警 - 先创建告警再创建事件以支持外键关联

        Returns:
            tuple: (事件对象列表, 新告警列表)
        """
        if not events:
            return [], []

        new_alert_events = []
        existing_alert_events = []

        active_alerts_map = {
            alert.monitor_instance_id: alert for alert in self.active_alerts
        }

        for event in events:
            instance_id = event["instance_id"]
            if instance_id in active_alerts_map:
                alert = active_alerts_map[instance_id]
                event["alert_id"] = alert.id
                event["_alert_obj"] = alert
                existing_alert_events.append(event)
            else:
                new_alert_events.append(event)

        new_alerts = []
        if new_alert_events:
            new_alerts = self._create_alerts_from_events(new_alert_events)

            if len(new_alerts) != len(new_alert_events):
                logger.error(
                    f"Alert creation mismatch: expected {len(new_alert_events)}, "
                    f"got {len(new_alerts)} for policy {self.policy.id}"
                )

            alert_map = {alert.monitor_instance_id: alert for alert in new_alerts}
            for event in new_alert_events:
                alert = alert_map.get(event["instance_id"])
                if alert:
                    event["alert_id"] = alert.id
                    event["_alert_obj"] = alert
                else:
                    logger.error(
                        f"Failed to get alert for event instance {event['instance_id']} "
                        f"in policy {self.policy.id}"
                    )
                    event["alert_id"] = None

        valid_events = [
            e for e in (new_alert_events + existing_alert_events) if e.get("alert_id")
        ]

        if len(valid_events) != len(new_alert_events) + len(existing_alert_events):
            logger.warning(
                f"Filtered out {len(new_alert_events) + len(existing_alert_events) - len(valid_events)} "
                f"events without alert_id for policy {self.policy.id}"
            )

        event_objs = self.create_events(valid_events)

        if existing_alert_events:
            self._update_existing_alerts_from_events(existing_alert_events)

        logger.info(
            f"Created events and alerts: "
            f"{len(new_alert_events)} new alerts, "
            f"{len(existing_alert_events)} existing alerts, "
            f"{len(event_objs)} events created"
        )

        return event_objs, new_alerts

    def _create_alerts_from_events(self, events):
        """从事件数据创建告警（不依赖事件对象）"""
        if not events:
            return []

        create_alerts = []

        for event in events:
            if event["level"] != "no_data":
                alert_type = "alert"
                level = event["level"]
                value = event["value"]
                content = event["content"]
            else:
                alert_type = "no_data"
                level = self.policy.no_data_level
                value = None
                content = "no data"

            create_alerts.append(
                MonitorAlert(
                    policy_id=self.policy.id,
                    monitor_instance_id=event["instance_id"],
                    monitor_instance_name=self.instances_map.get(
                        event["instance_id"], event["instance_id"]
                    ),
                    alert_type=alert_type,
                    level=level,
                    value=value,
                    content=content,
                    status="new",
                    start_event_time=self.policy.last_run_time,
                    operator="",
                )
            )

        new_alerts = MonitorAlert.objects.bulk_create(
            create_alerts, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE
        )

        if not new_alerts or not hasattr(new_alerts[0], "id"):
            instance_ids = [event["instance_id"] for event in events]
            new_alerts = list(
                MonitorAlert.objects.filter(
                    policy_id=self.policy.id,
                    monitor_instance_id__in=instance_ids,
                    start_event_time=self.policy.last_run_time,
                    status="new",
                ).order_by("id")
            )

        logger.info(f"Created {len(new_alerts)} new alerts for policy {self.policy.id}")
        return new_alerts

    def _update_existing_alerts_from_events(self, event_data_list):
        """更新已有告警的等级和内容（如果新事件级别更高）"""
        if not event_data_list:
            return

        alert_level_updates = []

        for event_data in event_data_list:
            alert = event_data.get("_alert_obj")
            if not alert:
                logger.warning(
                    f"Event data missing _alert_obj: {event_data.get('instance_id')}"
                )
                continue

            if event_data.get("level") == "no_data":
                continue

            event_level = event_data.get("level")
            current_weight = AlertConstants.LEVEL_WEIGHT.get(event_level, 0)
            alert_weight = AlertConstants.LEVEL_WEIGHT.get(alert.level, 0)

            if current_weight > alert_weight:
                alert.level = event_level
                alert.value = event_data.get("value")
                alert.content = event_data.get("content")
                alert_level_updates.append(alert)
                logger.debug(
                    f"Upgrading alert {alert.id} level from {alert.level} to {event_level}"
                )

        if alert_level_updates:
            MonitorAlert.objects.bulk_update(
                alert_level_updates,
                ["level", "value", "content"],
                batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE,
            )
            logger.info(
                f"Updated {len(alert_level_updates)} alerts with higher severity levels"
            )

    def send_notice(self, event_obj):
        """发送告警通知"""
        title = f"告警通知：{self.policy.name}"
        content = f"告警内容：{event_obj.content}"

        try:
            send_result = SystemMgmtUtils.send_msg_with_channel(
                self.policy.notice_type_id, title, content, self.policy.notice_users
            )
            if send_result.get("result") is False:
                logger.error(
                    f"send notice failed for policy {self.policy.name}: {send_result.get('message', 'Unknown error')}"
                )
            else:
                logger.info(
                    f"send notice success for policy {self.policy.name}: {send_result}"
                )
        except Exception as e:
            logger.error(
                f"send notice exception for policy {self.policy.name}: {e}",
                exc_info=True,
            )

        return []

    def notify_events(self, event_objs):
        """批量发送事件通知"""
        events_to_notify = []

        for event in event_objs:
            if event.level == "info":
                continue
            if event.level == "no_data" and self.policy.no_data_alert <= 0:
                continue
            events_to_notify.append(event)

        for event in events_to_notify:
            notice_results = self.send_notice(event)
            event.notice_result = notice_results

        if events_to_notify:
            MonitorEvent.objects.bulk_update(
                events_to_notify,
                ["notice_result"],
                batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE,
            )
