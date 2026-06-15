import uuid

from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import MonitorAlert, MonitorEvent, MonitorEventRawData
from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier
from apps.monitor.utils.dimension import format_dimension_str
from apps.core.logger import celery_logger as logger


class EventAlertManager:
    def __init__(self, policy, instances_map: dict, active_alerts):
        self.policy = policy
        self.instances_map = instances_map
        self.active_alerts = active_alerts

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
                    notice_result=[],
                    event_time=self.policy.last_run_time,
                )
            )
            if event.get("raw_data"):
                events_with_raw_data.append({"event_id": event_id, "raw_data": event["raw_data"]})

        event_objs = MonitorEvent.objects.bulk_create(create_events, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

        if not event_objs or not hasattr(event_objs[0], "id"):
            event_objs = list(
                MonitorEvent.objects.filter(policy_id=self.policy.id, event_time=self.policy.last_run_time).order_by("-created_at")[
                    : len(create_events)
                ]
            )

        if events_with_raw_data:
            self._create_raw_data_records(events_with_raw_data, event_objs)

        return event_objs

    def _create_raw_data_records(self, events_with_raw_data, event_objs):
        event_obj_map = {obj.id: obj for obj in event_objs}

        # event_obj_map 是本轮刚建/回查事件的权威集合；仅对不在其中的少数 id 做一次批量存在性兜底，
        # 取代原来逐条 .exists() 的 N 次 SELECT（正常情况下 missing_ids 为空，零额外查询）
        missing_ids = [info["event_id"] for info in events_with_raw_data if info["event_id"] not in event_obj_map]
        existing_missing = set()
        if missing_ids:
            existing_missing = set(MonitorEvent.objects.filter(id__in=missing_ids).values_list("id", flat=True))

        raw_data_objects = [
            MonitorEventRawData(event_id=info["event_id"], data=info["raw_data"])
            for info in events_with_raw_data
            if info["event_id"] in event_obj_map or info["event_id"] in existing_missing
        ]

        if raw_data_objects:
            # 逐行 save() 改批量 bulk_create——S3JSONField 的上传在 pre_save 完成（bulk_create 会调用 pre_save），
            # 行为与 save() 一致，仅把 N 次 INSERT 压成批量
            MonitorEventRawData.objects.bulk_create(raw_data_objects, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
            logger.info(f"Created {len(raw_data_objects)} raw data records for policy {self.policy.id}")

    def create_events_and_alerts(self, events):
        if not events:
            return [], []

        new_alert_events = []
        existing_alert_events = []

        active_alerts_map = {
            self._build_alert_key(self._get_alert_metric_instance_id(alert), alert.alert_type): alert for alert in self.active_alerts
        }

        for event in events:
            metric_instance_id = event.get("metric_instance_id", "")
            alert_key = self._build_alert_key(metric_instance_id, self._get_event_alert_type(event))
            if alert_key in active_alerts_map:
                alert = active_alerts_map[alert_key]
                event["alert_id"] = alert.id
                event["_alert_obj"] = alert
                existing_alert_events.append(event)
            else:
                new_alert_events.append(event)

        new_alerts = []
        if new_alert_events:
            new_alerts = self._create_alerts_from_events(new_alert_events)

            if len(new_alerts) != len(new_alert_events):
                logger.error(f"Alert creation mismatch: expected {len(new_alert_events)}, got {len(new_alerts)} for policy {self.policy.id}")

            alert_map = {self._build_alert_key(alert.metric_instance_id, alert.alert_type): alert for alert in new_alerts}
            for event in new_alert_events:
                alert = alert_map.get(
                    self._build_alert_key(
                        event.get("metric_instance_id", ""),
                        self._get_event_alert_type(event),
                    )
                )
                if alert:
                    event["alert_id"] = alert.id
                    event["_alert_obj"] = alert
                else:
                    logger.error(f"Failed to get alert for event metric_instance {event.get('metric_instance_id')} in policy {self.policy.id}")
                    event["alert_id"] = None

        valid_events = [e for e in (new_alert_events + existing_alert_events) if e.get("alert_id")]

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

    def _get_event_alert_type(self, event) -> str:
        return "no_data" if event.get("level") == "no_data" else "alert"

    def _build_alert_key(self, metric_instance_id: str, alert_type: str) -> tuple:
        return metric_instance_id, alert_type

    def _create_alerts_from_events(self, events):
        if not events:
            return []

        create_alerts = []

        for event in events:
            monitor_instance_id = event.get("monitor_instance_id", "")
            metric_instance_id = event.get("metric_instance_id", "")
            dimensions = event.get("dimensions", {})

            instance_name = self.instances_map.get(monitor_instance_id, monitor_instance_id)

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
                    monitor_instance_name=instance_name,
                    alert_type=alert_type,
                    level=level,
                    value=value,
                    content=content,
                    status="new",
                    start_event_time=self.policy.last_run_time,
                    operator="",
                    notice_type_ids=self.policy.notice_type_ids,
                    notice_users=self.policy.notice_users,
                )
            )

        new_alerts = MonitorAlert.objects.bulk_create(create_alerts, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)

        if not new_alerts or not hasattr(new_alerts[0], "id"):
            metric_instance_ids = [event.get("metric_instance_id", "") for event in events]
            new_alerts = list(
                MonitorAlert.objects.filter(
                    policy_id=self.policy.id,
                    metric_instance_id__in=metric_instance_ids,
                    start_event_time=self.policy.last_run_time,
                    status="new",
                ).order_by("id")
            )

        logger.info(f"Created {len(new_alerts)} new alerts for policy {self.policy.id}")

        if new_alerts and self.policy.notice:
            AlertLifecycleNotifier(self.policy).notify_alerts(new_alerts, action="created")

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
                logger.warning(f"Event data missing _alert_obj: {event_data.get('metric_instance_id')}")
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
                logger.debug(f"Upgrading alert {alert.id} level from {alert.level} to {event_level}")

        if alert_level_updates:
            MonitorAlert.objects.bulk_update(
                alert_level_updates,
                ["level", "value", "content"],
                batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE,
            )
            logger.info(f"Updated {len(alert_level_updates)} alerts with higher severity levels")

            if self.policy.notice:
                AlertLifecycleNotifier(self.policy).notify_alerts(alert_level_updates, action="upgraded")
