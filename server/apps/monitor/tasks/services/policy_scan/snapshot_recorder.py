"""快照记录服务 - 负责告警生命周期的指标快照记录"""

from datetime import datetime, timezone, timedelta

from django.db import transaction

from apps.monitor.models import MonitorEventRawData, MonitorAlertMetricSnapshot
from apps.monitor.tasks.utils.policy_calculate import _parse_finite_float
from apps.monitor.tasks.utils.policy_methods import (
    COMPARE_MODE_ABSOLUTE,
    period_to_seconds,
)
from apps.monitor.utils.dimension import parse_instance_id
from apps.core.logger import celery_logger as logger


class SnapshotRecorder:
    """快照记录服务"""

    def __init__(self, policy, instances_map: dict, active_alerts, metric_query_service):
        self.policy = policy
        self.instances_map = instances_map
        self.active_alerts = active_alerts
        self.metric_query_service = metric_query_service
        self._overlay_value_maps = None

    def _get_alert_metric_instance_id(self, alert) -> str:
        """获取告警的 metric_instance_id，兼容旧数据"""
        if alert.metric_instance_id:
            return alert.metric_instance_id
        return str((alert.monitor_instance_id,))

    def record_snapshots_for_active_alerts(self, info_events=None, event_objs=None, new_alerts=None):
        """为活跃告警创建或更新指标快照 - 合并告警下所有事件的快照数据"""
        all_active_alerts = list(self.active_alerts)
        if new_alerts:
            all_active_alerts.extend(new_alerts)

        if not all_active_alerts:
            return

        instance_raw_data_map = self._build_instance_raw_data_map(event_objs, info_events)
        fallback_raw_data_map = self._query_fallback_raw_data_map(
            all_active_alerts, instance_raw_data_map
        )

        event_map = {}
        if event_objs:
            for event_obj in event_objs:
                event_map.setdefault(event_obj.alert_id, []).append(event_obj)

        new_alert_ids = {alert.id for alert in new_alerts} if new_alerts else set()

        for alert in all_active_alerts:
            metric_id = self._get_alert_metric_instance_id(alert)
            is_new_alert = alert.id in new_alert_ids
            is_no_data_alert = alert.alert_type == "no_data"
            related_events = event_map.get(alert.id, [])
            # 无数据告警只保留「告警前一个点 + 之后的空窗」。阈值窗口里残留的
            # 采样点（info/event raw_data）不能按 metric_instance_id 贴过来。
            raw_data = {} if is_no_data_alert else instance_raw_data_map.get(metric_id, {})

            if not raw_data and not is_no_data_alert:
                raw_data = fallback_raw_data_map.get(metric_id, {})

            # 无数据告警即使没有 raw_data 也需要记录快照（记录"仍然无数据"状态）
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
            raw_data_objs = MonitorEventRawData.objects.filter(event_id__in=event_ids).select_related("event")

            for raw_data_obj in raw_data_objs:
                event = raw_data_obj.event
                metric_id = event.metric_instance_id or str((event.monitor_instance_id,))
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

    def _query_fallback_raw_data_map(self, alerts, instance_raw_data_map):
        """只为本轮取不到 raw_data 的历史阈值告警按实例范围补查。

        - 只把 miss 的告警所属监控实例编进 selector，不整库拉取；
        - 结果 key 按当前 group_by 构造，历史 metric_instance_id 维度数不一致
          （group_by 已变更）时直接跳过，避免每轮必走且永远命中不了的空转。
        """
        group_by_keys = list(self.metric_query_service.get_result_group_by() or [])
        wanted = set()
        instance_ids = []
        mismatched = 0
        for alert in alerts:
            if alert.alert_type == "no_data":
                continue
            metric_id = self._get_alert_metric_instance_id(alert)
            if instance_raw_data_map.get(metric_id):
                continue
            if len(parse_instance_id(metric_id)) != len(group_by_keys):
                mismatched += 1
                continue
            wanted.add(metric_id)
            instance_ids.append(alert.monitor_instance_id)

        if mismatched:
            logger.debug(
                "event=snapshot_fallback_skipped policy_id=%s reason=group_by_mismatch count=%s",
                self.policy.id,
                mismatched,
            )
        if not wanted:
            return {}

        data = self.metric_query_service.query_policy_window_metrics(
            self.policy.period, list(dict.fromkeys(instance_ids))
        )
        fallback_raw_data_map = {}
        for metric_info in data.get("data", {}).get("result", []):
            current_metric_id = str(tuple(metric_info["metric"].get(key) for key in group_by_keys))
            if current_metric_id in wanted:
                fallback_raw_data_map[current_metric_id] = metric_info
        return fallback_raw_data_map

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
        with transaction.atomic():
            snapshot_obj, created = MonitorAlertMetricSnapshot.objects.get_or_create(
                alert_id=alert.id,
                defaults={
                    "policy_id": self.policy.id,
                    "monitor_instance_id": alert.monitor_instance_id,
                    "snapshots": [],
                },
            )
            if not created:
                # Re-fetch with row lock to prevent lost-update on concurrent appends
                snapshot_obj = MonitorAlertMetricSnapshot.objects.select_for_update().get(pk=snapshot_obj.pk)

            has_new_snapshot = False

            if is_new_alert and created:
                metric_id = self._get_alert_metric_instance_id(alert)
                pre_alert_snapshot = self._build_pre_alert_snapshot(
                    metric_id, snapshot_time, monitor_instance_id=alert.monitor_instance_id
                )
                if pre_alert_snapshot:
                    snapshot_obj.snapshots.append(pre_alert_snapshot)
                    has_new_snapshot = True
                    logger.info(f"Added pre-alert snapshot for alert {alert.id}, metric_instance {metric_id}")

            if is_no_data_alert:
                raw_data = {}

            if event_objs:
                for event_obj in event_objs:
                    event_snapshot = {
                        "type": "event",
                        "event_id": event_obj.id,
                        "event_time": event_obj.event_time.isoformat() if event_obj.event_time else None,
                        "snapshot_time": snapshot_time.isoformat(),
                        "raw_data": raw_data,
                        **self._snapshot_compare_fields(alert, raw_data, event_obj),
                    }

                    existing_event_ids = [s.get("event_id") for s in snapshot_obj.snapshots if s.get("type") == "event"]
                    if event_obj.id not in existing_event_ids:
                        snapshot_obj.snapshots.append(event_snapshot)
                        has_new_snapshot = True
                        logger.debug(f"Added event snapshot for alert {alert.id}, event {event_obj.id}")

            elif raw_data:
                snapshot_time_str = snapshot_time.isoformat()
                existing_snapshot_times = [s.get("snapshot_time") for s in snapshot_obj.snapshots if s.get("type") == "info"]
                if snapshot_time_str not in existing_snapshot_times:
                    info_snapshot = {
                        "type": "info",
                        "snapshot_time": snapshot_time_str,
                        "raw_data": raw_data,
                        **self._snapshot_compare_fields(alert, raw_data),
                    }
                    snapshot_obj.snapshots.append(info_snapshot)
                    has_new_snapshot = True
                    logger.debug(f"Added info snapshot for alert {alert.id}, time {snapshot_time_str}")

            elif is_no_data_alert:
                snapshot_time_str = snapshot_time.isoformat()
                existing_snapshot_times = [s.get("snapshot_time") for s in snapshot_obj.snapshots if s.get("type") == "no_data"]
                if snapshot_time_str not in existing_snapshot_times:
                    no_data_snapshot = {
                        "type": "no_data",
                        "event_time": snapshot_time_str,
                        "snapshot_time": snapshot_time_str,
                        "raw_data": {},
                    }
                    snapshot_obj.snapshots.append(no_data_snapshot)
                    has_new_snapshot = True
                    logger.debug(f"Added no_data snapshot for alert {alert.id}, time {snapshot_time_str}")

            if has_new_snapshot:
                snapshot_obj.save(update_fields=["snapshots", "updated_at"])
                logger.info(f"Saved snapshot for alert {alert.id}, total snapshots: {len(snapshot_obj.snapshots)}")
            else:
                logger.debug(f"No new snapshot data for alert {alert.id}, skipping save")

    def _build_pre_alert_snapshot(
        self, metric_instance_id, current_snapshot_time, monitor_instance_id=None
    ):
        """构建告警前快照数据；只查该告警所属实例，不按策略全范围拉取。"""
        period_seconds = period_to_seconds(self.policy.period)
        pre_alert_time = datetime.fromtimestamp(current_snapshot_time.timestamp() - period_seconds, tz=timezone.utc)

        min_time = datetime.now(timezone.utc) - timedelta(days=7)
        if pre_alert_time < min_time:
            logger.warning(
                f"Pre-alert time {pre_alert_time} too early for policy {self.policy.id}, "
                f"skipping pre-alert snapshot for metric_instance {metric_instance_id}"
            )
            return None

        group_by_keys = self.metric_query_service.get_result_group_by()
        instance_ids = [monitor_instance_id] if monitor_instance_id else None

        try:
            pre_alert_metrics = self.metric_query_service.query_policy_window_metrics(
                self.policy.period,
                instance_ids=instance_ids,
                end_timestamp=int(pre_alert_time.timestamp()),
            )
        except Exception as e:
            logger.error(f"Failed to query pre-alert metrics for policy {self.policy.id}: {e}")
            return None

        raw_data = {}
        for metric_info in pre_alert_metrics.get("data", {}).get("result", []):
            current_metric_id = str(tuple([metric_info["metric"].get(key) for key in group_by_keys]))

            if current_metric_id == metric_instance_id:
                raw_data = metric_info
                break

        if not raw_data:
            logger.warning(
                f"No pre-alert data found for policy {self.policy.id}, metric_instance {metric_instance_id} at time {pre_alert_time.isoformat()}"
            )
            return None

        logger.info(f"Built pre-alert snapshot for policy {self.policy.id}, metric_instance {metric_instance_id}")
        snapshot = {
            "type": "pre_alert",
            "snapshot_time": pre_alert_time.isoformat(),
            "raw_data": raw_data,
        }
        snapshot.update(self._compare_fields_for_raw(metric_instance_id, raw_data))
        return snapshot

    def _overlay_maps(self):
        if self._overlay_value_maps is None:
            self._overlay_value_maps = self.metric_query_service.query_overlay_last_values()
        return self._overlay_value_maps

    def _snapshot_compare_fields(self, alert, raw_data, event_obj=None):
        metric_id = self._get_alert_metric_instance_id(alert)
        event_value = getattr(event_obj, "value", None) if event_obj is not None else None
        return self._compare_fields_for_raw(metric_id, raw_data, event_value)

    def _compare_fields_for_raw(self, metric_instance_id, raw_data, event_value=None):
        compared = _parse_finite_float(event_value)
        if compared is None:
            values = (raw_data or {}).get("values") or []
            if values and isinstance(values[-1], (list, tuple)) and len(values[-1]) >= 2:
                compared = _parse_finite_float(values[-1][1])
        current_map, baseline_map = self._overlay_maps()
        current = current_map.get(metric_instance_id)
        baseline = baseline_map.get(metric_instance_id)
        compare_mode = getattr(self.policy, "compare_mode", None) or COMPARE_MODE_ABSOLUTE
        if compare_mode in ("", COMPARE_MODE_ABSOLUTE) and compared is not None:
            current = compared
            baseline = None
        result_unit = self.metric_query_service.get_effective_calculation_unit() or ""
        return {
            "current_value": current,
            "baseline_value": baseline,
            "compared_value": compared,
            "result_unit": result_unit,
        }
