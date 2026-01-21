"""快照记录服务 - 负责告警生命周期的指标快照记录"""

from datetime import datetime, timezone, timedelta

from apps.monitor.models import MonitorEventRawData, MonitorAlertMetricSnapshot
from apps.monitor.tasks.utils.policy_methods import METHOD, period_to_seconds
from apps.core.logger import celery_logger as logger


class SnapshotRecorder:
    """快照记录服务"""

    def __init__(
        self, policy, instances_map: dict, active_alerts, metric_query_service
    ):
        self.policy = policy
        self.instances_map = instances_map
        self.active_alerts = active_alerts
        self.metric_query_service = metric_query_service

    def record_snapshots_for_active_alerts(
        self, info_events=None, event_objs=None, new_alerts=None
    ):
        """为活跃告警创建或更新指标快照 - 合并告警下所有事件的快照数据"""
        all_active_alerts = list(self.active_alerts)
        if new_alerts:
            all_active_alerts.extend(new_alerts)

        if not all_active_alerts:
            return

        instance_raw_data_map = self._build_instance_raw_data_map(
            event_objs, info_events
        )

        event_map = {}
        if event_objs:
            for event_obj in event_objs:
                instance_id = event_obj.monitor_instance_id
                if instance_id not in event_map:
                    event_map[instance_id] = []
                event_map[instance_id].append(event_obj)

        new_alert_instance_ids = (
            {alert.monitor_instance_id for alert in new_alerts} if new_alerts else set()
        )

        for alert in all_active_alerts:
            instance_id = alert.monitor_instance_id
            is_new_alert = instance_id in new_alert_instance_ids
            related_events = event_map.get(instance_id, [])
            raw_data = instance_raw_data_map.get(instance_id, {})

            if not raw_data:
                raw_data = self._query_fallback_raw_data(instance_id)

            if related_events or raw_data or is_new_alert:
                self._update_alert_snapshot(
                    alert,
                    related_events,
                    raw_data,
                    self.policy.last_run_time,
                    is_new_alert,
                )

    def _build_instance_raw_data_map(self, event_objs, info_events):
        """构建实例ID到原始数据的映射"""
        instance_raw_data_map = {}

        if event_objs:
            event_ids = [event_obj.id for event_obj in event_objs]
            raw_data_objs = MonitorEventRawData.objects.filter(
                event_id__in=event_ids
            ).select_related("event")

            for raw_data_obj in raw_data_objs:
                instance_id = raw_data_obj.event.monitor_instance_id
                instance_raw_data_map[instance_id] = raw_data_obj.data

        if info_events:
            for event in info_events:
                instance_id = event["instance_id"]
                if event.get("raw_data") and instance_id not in instance_raw_data_map:
                    instance_raw_data_map[instance_id] = event["raw_data"]

        return instance_raw_data_map

    def _query_fallback_raw_data(self, instance_id):
        """查询兜底原始数据（用于历史活跃告警）"""
        fallback_data = self.metric_query_service.query_raw_metrics(self.policy.period)
        for metric_info in fallback_data.get("data", {}).get("result", []):
            metric_instance_id = str(
                tuple(
                    [
                        metric_info["metric"].get(i)
                        for i in self.metric_query_service.instance_id_keys
                    ]
                )
            )
            if metric_instance_id == instance_id:
                return metric_info
        return {}

    def _update_alert_snapshot(
        self, alert, event_objs, raw_data, snapshot_time, is_new_alert=False
    ):
        """更新告警的快照数据"""
        snapshot_obj, created = MonitorAlertMetricSnapshot.objects.get_or_create(
            alert_id=alert.id,
            defaults={
                "policy_id": self.policy.id,
                "monitor_instance_id": alert.monitor_instance_id,
                "snapshots": [],
            },
        )

        has_new_snapshot = False

        if is_new_alert and created:
            pre_alert_snapshot = self._build_pre_alert_snapshot(
                alert.monitor_instance_id, snapshot_time
            )
            if pre_alert_snapshot:
                snapshot_obj.snapshots.append(pre_alert_snapshot)
                has_new_snapshot = True
                logger.info(
                    f"Added pre-alert snapshot for alert {alert.id}, instance {alert.monitor_instance_id}"
                )

        if event_objs:
            for event_obj in event_objs:
                event_snapshot = {
                    "type": "event",
                    "event_id": event_obj.id,
                    "event_time": event_obj.event_time.isoformat()
                    if event_obj.event_time
                    else None,
                    "snapshot_time": snapshot_time.isoformat(),
                    "raw_data": raw_data if raw_data else {},
                }

                existing_event_ids = [
                    s.get("event_id")
                    for s in snapshot_obj.snapshots
                    if s.get("type") == "event"
                ]
                if event_obj.id not in existing_event_ids:
                    snapshot_obj.snapshots.append(event_snapshot)
                    has_new_snapshot = True
                    logger.debug(
                        f"Added event snapshot for alert {alert.id}, event {event_obj.id}"
                    )

        elif raw_data:
            snapshot_time_str = snapshot_time.isoformat()
            existing_snapshot_times = [
                s.get("snapshot_time")
                for s in snapshot_obj.snapshots
                if s.get("type") == "info"
            ]
            if snapshot_time_str not in existing_snapshot_times:
                info_snapshot = {
                    "type": "info",
                    "snapshot_time": snapshot_time_str,
                    "raw_data": raw_data,
                }
                snapshot_obj.snapshots.append(info_snapshot)
                has_new_snapshot = True
                logger.debug(
                    f"Added info snapshot for alert {alert.id}, time {snapshot_time_str}"
                )

        if has_new_snapshot:
            snapshot_obj.save(update_fields=["snapshots", "updated_at"])
            logger.info(
                f"Saved snapshot for alert {alert.id}, total snapshots: {len(snapshot_obj.snapshots)}"
            )
        else:
            logger.debug(f"No new snapshot data for alert {alert.id}, skipping save")

    def _build_pre_alert_snapshot(self, instance_id, current_snapshot_time):
        """构建告警前快照数据"""
        period_seconds = period_to_seconds(self.policy.period)
        pre_alert_time = datetime.fromtimestamp(
            current_snapshot_time.timestamp() - period_seconds, tz=timezone.utc
        )

        min_time = datetime.now(timezone.utc) - timedelta(days=7)
        if pre_alert_time < min_time:
            logger.warning(
                f"Pre-alert time {pre_alert_time} too early for policy {self.policy.id}, "
                f"skipping pre-alert snapshot for instance {instance_id}"
            )
            return None

        end_timestamp = int(pre_alert_time.timestamp())
        start_timestamp = end_timestamp - period_seconds
        query = self.metric_query_service.format_pmq()
        step = self.metric_query_service.format_period(self.policy.period)
        group_by = ",".join(self.metric_query_service.instance_id_keys)

        method = METHOD.get(self.policy.algorithm)
        if not method:
            logger.warning(
                f"Invalid algorithm {self.policy.algorithm} for policy {self.policy.id}"
            )
            return None

        try:
            pre_alert_metrics = method(
                query, start_timestamp, end_timestamp, step, group_by
            )
        except Exception as e:
            logger.error(
                f"Failed to query pre-alert metrics for policy {self.policy.id}: {e}"
            )
            return None

        raw_data = {}
        for metric_info in pre_alert_metrics.get("data", {}).get("result", []):
            metric_instance_id = str(
                tuple(
                    [
                        metric_info["metric"].get(key)
                        for key in self.metric_query_service.instance_id_keys
                    ]
                )
            )

            if self.instances_map and metric_instance_id not in self.instances_map:
                continue

            if metric_instance_id == instance_id:
                raw_data = metric_info
                break

        if not raw_data:
            logger.warning(
                f"No pre-alert data found for policy {self.policy.id}, instance {instance_id} "
                f"at time {pre_alert_time.isoformat()}"
            )
            return None

        logger.info(
            f"Built pre-alert snapshot for policy {self.policy.id}, instance {instance_id}"
        )
        return {
            "type": "pre_alert",
            "snapshot_time": pre_alert_time.isoformat(),
            "raw_data": raw_data,
        }
