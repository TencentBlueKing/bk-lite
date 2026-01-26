"""监控策略扫描执行器 - 主流程编排"""

from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.models import (
    MonitorInstanceOrganization,
    MonitorAlert,
    MonitorInstance,
)
from apps.monitor.tasks.services.policy_scan.metric_query import MetricQueryService
from apps.monitor.tasks.services.policy_scan.alert_detector import AlertDetector
from apps.monitor.tasks.services.policy_scan.event_alert_manager import (
    EventAlertManager,
)
from apps.monitor.tasks.services.policy_scan.snapshot_recorder import SnapshotRecorder
from apps.core.logger import celery_logger as logger


class MonitorPolicyScan:
    """监控策略扫描执行器 - 负责流程编排"""

    def __init__(self, policy):
        self.policy = policy
        self.instances_map = self._build_instances_map()
        self.active_alerts = self._get_active_alerts()

        self.metric_query_service = MetricQueryService(policy, self.instances_map)
        self.alert_detector = AlertDetector(
            policy, self.instances_map, self.active_alerts, self.metric_query_service
        )
        self.event_alert_manager = EventAlertManager(
            policy, self.instances_map, self.active_alerts
        )
        self.snapshot_recorder = SnapshotRecorder(
            policy, self.instances_map, self.active_alerts, self.metric_query_service
        )

    def _get_active_alerts(self):
        """获取策略的活动告警"""
        qs = MonitorAlert.objects.filter(policy_id=self.policy.id, status="new")
        if self.policy.source:
            qs = qs.filter(monitor_instance_id__in=self.instances_map.keys())
        return qs

    def _build_instances_map(self):
        """构建策略适用的实例映射"""
        if not self.policy.source:
            return {}

        source_type = self.policy.source["type"]
        source_values = self.policy.source["values"]

        instance_list = self._get_instance_list_by_source(source_type, source_values)

        instances = MonitorInstance.objects.filter(
            monitor_object_id=self.policy.monitor_object_id,
            id__in=instance_list,
            is_deleted=False,
        )
        return {instance.id: instance.name for instance in instances}

    def _get_instance_list_by_source(self, source_type, source_values):
        """根据来源类型获取实例列表"""
        if source_type == "instance":
            return source_values

        if source_type == "organization":
            return list(
                MonitorInstanceOrganization.objects.filter(
                    monitor_instance__monitor_object_id=self.policy.monitor_object_id,
                    organization__in=source_values,
                ).values_list("monitor_instance_id", flat=True)
            )

        return []

    def _execute_step(self, step_name, func, *args, critical=False, **kwargs):
        """执行流程步骤，统一错误处理"""
        try:
            result = func(*args, **kwargs)
            logger.info(f"{step_name} completed for policy {self.policy.id}")
            return True, result
        except Exception as e:
            logger.error(
                f"Failed to {step_name.lower()} for policy {self.policy.id}: {e}",
                exc_info=True,
            )
            if critical:
                raise
            return False, None

    def _process_threshold_alerts(self):
        """处理阈值告警"""
        alert_events, info_events = self.alert_detector.detect_threshold_alerts()
        self.alert_detector.count_events(alert_events, info_events)
        self.alert_detector.recover_threshold_alerts()
        return alert_events, info_events

    def _process_no_data_alerts(self):
        """处理无数据告警"""
        no_data_events = self.alert_detector.detect_no_data_alerts()
        self.alert_detector.recover_no_data_alerts()
        return no_data_events

    def _create_events_alerts_and_notify(self, events):
        """创建事件、告警并发送通知"""
        if not events:
            return [], []

        success, result = self._execute_step(
            "Create events and alerts",
            self.event_alert_manager.create_events_and_alerts,
            events,
            critical=True,
        )
        if not success:
            return None, None

        event_objs, new_alerts = result
        logger.info(
            f"Created {len(event_objs)} events and {len(new_alerts)} new alerts"
        )

        if self.policy.notice and event_objs:
            self._execute_step(
                "Send notifications", self.event_alert_manager.notify_events, event_objs
            )

        return event_objs, new_alerts

    def _record_snapshots(self, info_events, event_objs, new_alerts):
        """记录告警生命周期快照"""
        has_active_alerts = bool(self.active_alerts) or bool(new_alerts)
        has_snapshot_data = bool(info_events) or bool(event_objs) or bool(new_alerts)

        if has_active_alerts and has_snapshot_data:
            self._execute_step(
                "Create metric snapshots",
                self.snapshot_recorder.record_snapshots_for_active_alerts,
                info_events=info_events,
                event_objs=event_objs,
                new_alerts=new_alerts,
            )

    def run(self):
        """执行监控策略扫描主流程"""
        if not self._pre_check():
            return

        alert_events, info_events, no_data_events = self._collect_events()

        events = alert_events + no_data_events
        result = self._create_events_alerts_and_notify(events)
        if result[0] is None:
            return
        event_objs, new_alerts = result

        self._record_snapshots(info_events, event_objs, new_alerts)

    def _pre_check(self):
        """前置检查"""
        if self.policy.source and not self.instances_map:
            logger.warning(
                f"Policy {self.policy.id} has source but no instances, skipping scan"
            )
            return False

        try:
            self._execute_step(
                "Set monitor instance key",
                self.metric_query_service.set_monitor_obj_instance_key,
                critical=True,
            )
        except Exception:
            return False

        return True

    def _collect_events(self):
        """收集告警事件"""
        alert_events, info_events, no_data_events = [], [], []

        if AlertConstants.THRESHOLD in self.policy.enable_alerts:
            success, result = self._execute_step(
                "Process threshold alerts", self._process_threshold_alerts
            )
            if success and result is not None:
                alert_events, info_events = result
                logger.info(
                    f"Threshold alerts: {len(alert_events)} alerts, {len(info_events)} info events"
                )

        if AlertConstants.NO_DATA in self.policy.enable_alerts:
            success, result = self._execute_step(
                "Process no-data alerts", self._process_no_data_alerts
            )
            if success and result is not None:
                no_data_events = result
                logger.info(f"No-data alerts: {len(no_data_events)} events")

        return alert_events, info_events, no_data_events
