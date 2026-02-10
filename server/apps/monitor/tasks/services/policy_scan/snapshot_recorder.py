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

    def _get_alert_metric_instance_id(self, alert) -> str:
        """获取告警的 metric_instance_id，兼容旧数据"""
        if alert.metric_instance_id:
            return alert.metric_instance_id
        return str((alert.monitor_instance_id,))

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
                metric_id = event_obj.metric_instance_id or str(
                    (event_obj.monitor_instance_id,)
                )
                if metric_id not in event_map:
                    event_map[metric_id] = []
                event_map[metric_id].append(event_obj)

        new_alert_metric_ids = (
            {self._get_alert_metric_instance_id(alert) for alert in new_alerts}
            if new_alerts
            else set()
        )

        for alert in all_active_alerts:
            metric_id = self._get_alert_metric_instance_id(alert)
            is_new_alert = metric_id in new_alert_metric_ids
            related_events = event_map.get(metric_id, [])
            raw_data = instance_raw_data_map.get(metric_id, {})

            if not raw_data:
                raw_data = self._query_fallback_raw_data(metric_id)

            # 无数据告警即使没有 raw_data 也需要记录快照（记录"仍然无数据"状态）
            is_no_data_alert = alert.alert_type == "no_data"

            if related_events or raw_data or is_new_alert or is_no_data_alert:
                self._update_alert_snapshot(
                    alert,
                    related_events,
                    raw_data,
                    self.policy.last_run_time,
                    is_new_alert,
                    is_no_data_alert,
                )

    def _build_instance_raw_data_map(self, event_objs, info_events):
        """构建 metric_instance_id 到原始数据的映射"""
        instance_raw_data_map = {}

        if event_objs:
            event_ids = [event_obj.id for event_obj in event_objs]
            raw_data_objs = MonitorEventRawData.objects.filter(
                event_id__in=event_ids
            ).select_related("event")

            for raw_data_obj in raw_data_objs:
                event = raw_data_obj.event
                metric_id = event.metric_instance_id or str(
                    (event.monitor_instance_id,)
                )
                instance_raw_data_map[metric_id] = raw_data_obj.data

        if info_events:
            for event in info_events:
                metric_id = event.get("metric_instance_id", "")
                if not metric_id:
                    monitor_id = event.get("monitor_instance_id", "")
                    metric_id = str((monitor_id,)) if monitor_id else ""
                if event.get("raw_data") and metric_id not in instance_raw_data_map:
                    instance_raw_data_map[metric_id] = event["raw_data"]

        return instance_raw_data_map

    def _query_fallback_raw_data(self, metric_instance_id):
        """查询兜底原始数据（用于历史活跃告警）"""
        fallback_data = self.metric_query_service.query_raw_metrics(self.policy.period)
        group_by_keys = self.policy.group_by or []
        for metric_info in fallback_data.get("data", {}).get("result", []):
            current_metric_id = str(
                tuple([metric_info["metric"].get(i) for i in group_by_keys])
            )
            if current_metric_id == metric_instance_id:
                return metric_info
        return {}

    def _update_alert_snapshot(
        self,
        alert,
        event_objs,
        raw_data,
        snapshot_time,
        is_new_alert=False,
        is_no_data_alert=False,
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
            metric_id = self._get_alert_metric_instance_id(alert)
            pre_alert_snapshot = self._build_pre_alert_snapshot(
                metric_id, snapshot_time
            )
            if pre_alert_snapshot:
                snapshot_obj.snapshots.append(pre_alert_snapshot)
                has_new_snapshot = True
                logger.info(
                    f"Added pre-alert snapshot for alert {alert.id}, metric_instance {metric_id}"
                )

        if event_objs and raw_data:
            for event_obj in event_objs:
                event_snapshot = {
                    "type": "event",
                    "event_id": event_obj.id,
                    "event_time": event_obj.event_time.isoformat()
                    if event_obj.event_time
                    else None,
                    "snapshot_time": snapshot_time.isoformat(),
                    "raw_data": raw_data,
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

        elif is_no_data_alert:
            snapshot_time_str = snapshot_time.isoformat()
            existing_snapshot_times = [
                s.get("snapshot_time")
                for s in snapshot_obj.snapshots
                if s.get("type") == "no_data"
            ]
            if snapshot_time_str not in existing_snapshot_times:
                no_data_snapshot = {
                    "type": "no_data",
                    "event_time": snapshot_time_str,
                    "snapshot_time": snapshot_time_str,
                    "raw_data": {},
                }
                snapshot_obj.snapshots.append(no_data_snapshot)
                has_new_snapshot = True
                logger.debug(
                    f"Added no_data snapshot for alert {alert.id}, time {snapshot_time_str}"
                )

        if has_new_snapshot:
            snapshot_obj.save(update_fields=["snapshots", "updated_at"])
            logger.info(
                f"Saved snapshot for alert {alert.id}, total snapshots: {len(snapshot_obj.snapshots)}"
            )
        else:
            logger.debug(f"No new snapshot data for alert {alert.id}, skipping save")

    def _build_pre_alert_snapshot(self, metric_instance_id, current_snapshot_time):
        """构建告警前快照数据"""
        period_seconds = period_to_seconds(self.policy.period)
        pre_alert_time = datetime.fromtimestamp(
            current_snapshot_time.timestamp() - period_seconds, tz=timezone.utc
        )

        min_time = datetime.now(timezone.utc) - timedelta(days=7)
        if pre_alert_time < min_time:
            logger.warning(
                f"Pre-alert time {pre_alert_time} too early for policy {self.policy.id}, "
                f"skipping pre-alert snapshot for metric_instance {metric_instance_id}"
            )
            return None

        end_timestamp = int(pre_alert_time.timestamp())
        start_timestamp = end_timestamp - period_seconds
        query = self.metric_query_service.format_pmq()
        step = self.metric_query_service.format_period(self.policy.period)
        group_by_keys = self.policy.group_by or []
        group_by = ",".join(group_by_keys)

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
            current_metric_id = str(
                tuple([metric_info["metric"].get(key) for key in group_by_keys])
            )

            if current_metric_id == metric_instance_id:
                raw_data = metric_info
                break

        if not raw_data:
            logger.warning(
                f"No pre-alert data found for policy {self.policy.id}, metric_instance {metric_instance_id} "
                f"at time {pre_alert_time.isoformat()}"
            )
            return None

        logger.info(
            f"Built pre-alert snapshot for policy {self.policy.id}, metric_instance {metric_instance_id}"
        )
        return {
            "type": "pre_alert",
            "snapshot_time": pre_alert_time.isoformat(),
            "raw_data": raw_data,
        }
