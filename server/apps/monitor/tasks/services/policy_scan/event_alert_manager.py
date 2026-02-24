"""事件告警管理服务 - 负责事件和告警的创建、通知"""

import uuid

from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import MonitorAlert, MonitorEvent, MonitorEventRawData
from apps.monitor.utils.dimension import format_dimension_str
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils
from apps.system_mgmt.models import Channel
from apps.core.logger import celery_logger as logger


class EventAlertManager:
    def __init__(self, policy, instances_map: dict, active_alerts):
        self.policy = policy
        self.instances_map = instances_map
        self.active_alerts = active_alerts
        self._is_alert_center = self._check_alert_center_channel()

    def create_events(self, events):
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
                    monitor_instance_id=event.get("monitor_instance_id", ""),
                    metric_instance_id=event.get("metric_instance_id", ""),
                    dimensions=event.get("dimensions", {}),
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
        if not events:
            return [], []

        new_alert_events = []
        existing_alert_events = []

        active_alerts_map = {
            self._get_alert_metric_instance_id(alert): alert
            for alert in self.active_alerts
        }

        for event in events:
            metric_instance_id = event.get("metric_instance_id", "")
            if metric_instance_id in active_alerts_map:
                alert = active_alerts_map[metric_instance_id]
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

            alert_map = {alert.metric_instance_id: alert for alert in new_alerts}
            for event in new_alert_events:
                alert = alert_map.get(event.get("metric_instance_id", ""))
                if alert:
                    event["alert_id"] = alert.id
                    event["_alert_obj"] = alert
                else:
                    logger.error(
                        f"Failed to get alert for event metric_instance {event.get('metric_instance_id')} "
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

    def _get_alert_metric_instance_id(self, alert) -> str:
        if alert.metric_instance_id:
            return alert.metric_instance_id
        return str((alert.monitor_instance_id,))

    def _create_alerts_from_events(self, events):
        if not events:
            return []

        create_alerts = []

        for event in events:
            monitor_instance_id = event.get("monitor_instance_id", "")
            metric_instance_id = event.get("metric_instance_id", "")
            dimensions = event.get("dimensions", {})

            instance_name = self.instances_map.get(
                monitor_instance_id, monitor_instance_id
            )
            dimension_str = self._format_dimension_str(dimensions)
            display_name = (
                f"{instance_name} - {dimension_str}" if dimension_str else instance_name
            )

            if event["level"] != "no_data":
                alert_type = "alert"
                level = event["level"]
                value = event["value"]
                content = event["content"]
            else:
                alert_type = "no_data"
                level = self.policy.no_data_level
                value = None
                content = event["content"]

            create_alerts.append(
                MonitorAlert(
                    policy_id=self.policy.id,
                    monitor_instance_id=monitor_instance_id,
                    metric_instance_id=metric_instance_id,
                    dimensions=dimensions,
                    monitor_instance_name=display_name,
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
            metric_instance_ids = [
                event.get("metric_instance_id", "") for event in events
            ]
            new_alerts = list(
                MonitorAlert.objects.filter(
                    policy_id=self.policy.id,
                    metric_instance_id__in=metric_instance_ids,
                    start_event_time=self.policy.last_run_time,
                    status="new",
                ).order_by("id")
            )

        logger.info(f"Created {len(new_alerts)} new alerts for policy {self.policy.id}")
        return new_alerts

    def _format_dimension_str(self, dimensions: dict) -> str:
        return format_dimension_str(dimensions)

    def _update_existing_alerts_from_events(self, event_data_list):
        if not event_data_list:
            return

        alert_level_updates = []

        for event_data in event_data_list:
            alert = event_data.get("_alert_obj")
            if not alert:
                logger.warning(
                    f"Event data missing _alert_obj: {event_data.get('metric_instance_id')}"
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
        events_to_notify = []

        for event in event_objs:
            if event.level == "info":
                continue
            if event.level == "no_data" and self.policy.no_data_alert <= 0:
                continue
            events_to_notify.append(event)

        if not events_to_notify:
            return

        if self._is_alert_center:
            self._push_to_alert_center(events_to_notify)
        else:
            for event in events_to_notify:
                notice_results = self.send_notice(event)
                event.notice_result = notice_results

            MonitorEvent.objects.bulk_update(
                events_to_notify,
                ["notice_result"],
                batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE,
            )

    def _check_alert_center_channel(self) -> bool:
        """检查通知渠道是否为告警中心（初始化时调用一次）"""
        if not self.policy.notice_type_id:
            return False
        # todo 获取Channel详情的nats方法
        channel = Channel.objects.filter(id=self.policy.notice_type_id).first()
        if not channel:
            return False
        return (
            channel.channel_type == "nats"
            and channel.config.get("method_name") == "receive_alert_events"
        )

    def _push_to_alert_center(self, events_to_notify):
        alert_events = []
        for event in events_to_notify:
            start_time = (
                str(int(event.event_time.timestamp())) if event.event_time else None
            )
            alert_events.append(
                {
                    "external_id": event.id,
                    "rule_id": str(event.policy_id),
                    "title": event.content,
                    "description": event.content,
                    "level": self._map_level_to_alert_center(event.level),
                    "value": float(event.value) if event.value is not None else None,
                    "action": "created",
                    "start_time": start_time,
                    "resource_id": event.monitor_instance_id,
                    "resource_name": self.instances_map.get(
                        event.monitor_instance_id, ""
                    ),
                    "tags": event.dimensions,
                    "labels": {
                        "policy_name": self.policy.name,
                        "metric_instance_id": event.metric_instance_id,
                        "alert_id": event.alert_id,
                    },
                }
            )

        content = {
            "source_id": "nats",
            "pusher": "lite-monitor",
            "events": alert_events,
        }
        try:
            send_result = SystemMgmtUtils.send_msg_with_channel(
                self.policy.notice_type_id, "", content, []
            )
            if send_result.get("result") is False:
                logger.error(
                    f"Push to alert center failed for policy {self.policy.name}: "
                    f"{send_result.get('message', 'Unknown error')}"
                )
            else:
                logger.info(
                    f"Push to alert center success for policy {self.policy.name}: "
                    f"{len(alert_events)} events"
                )
        except Exception as e:
            logger.error(
                f"Push to alert center exception for policy {self.policy.name}: {e}",
                exc_info=True,
            )

    def _map_level_to_alert_center(self, level):
        """映射告警级别到告警中心格式: 0-致命, 1-错误, 2-预警, 3-提醒"""
        level_map = {
            "critical": "0",
            "error": "1",
            "warning": "2",
            "info": "3",
            "no_data": "2",
        }
        return level_map.get(level, "3")

        content = {"events": alert_events}
        try:
            send_result = SystemMgmtUtils.send_msg_with_channel(
                self.policy.notice_type_id, "", content, []
            )
            if send_result.get("result") is False:
                logger.error(
                    f"Push to alert center failed for policy {self.policy.name}: "
                    f"{send_result.get('message', 'Unknown error')}"
                )
            else:
                logger.info(
                    f"Push to alert center success for policy {self.policy.name}: "
                    f"{len(alert_events)} events"
                )
        except Exception as e:
            logger.error(
                f"Push to alert center exception for policy {self.policy.name}: {e}",
                exc_info=True,
            )
