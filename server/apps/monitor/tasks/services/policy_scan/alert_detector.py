"""告警检测服务 - 负责告警事件的检测和恢复"""

from string import Template

from django.db.models import F

from apps.monitor.models import MonitorAlert
from apps.monitor.tasks.utils.policy_calculate import vm_to_dataframe, calculate_alerts
from apps.core.logger import celery_logger as logger


class AlertDetector:
    """告警检测服务

    负责:
    - 阈值告警检测
    - 无数据告警检测
    - 告警恢复处理
    - 告警计数管理
    """

    def __init__(
        self, policy, instances_map: dict, active_alerts, metric_query_service
    ):
        self.policy = policy
        self.instances_map = instances_map
        self.active_alerts = active_alerts
        self.metric_query_service = metric_query_service

    def detect_threshold_alerts(self):
        """检测阈值告警

        Returns:
            tuple: (告警事件列表, 正常事件列表)
        """
        vm_data = self.metric_query_service.query_aggregation_metrics(
            self.policy.period
        )
        vm_data = self.metric_query_service.convert_metric_values(vm_data)

        df = vm_to_dataframe(
            vm_data.get("data", {}).get("result", []),
            self.metric_query_service.instance_id_keys,
        )

        template_context = {
            "monitor_object": self.policy.monitor_object.name
            if self.policy.monitor_object
            else "",
            "metric_name": self._get_metric_display_name(),
            "instances_map": self.instances_map,
        }

        alert_events, info_events = calculate_alerts(
            self.policy.alert_name, df, self.policy.threshold, template_context
        )

        if self.policy.source:
            alert_events = self._filter_events_by_instance_scope(alert_events)
            info_events = self._filter_events_by_instance_scope(info_events)

        if alert_events:
            self._log_alert_events(alert_events, vm_data)

        return alert_events, info_events

    def _get_metric_display_name(self):
        """获取指标展示名称"""
        metric = self.metric_query_service.metric
        if metric:
            return metric.display_name or metric.name
        return self.policy.query_condition.get("metric_id", "")

    def detect_no_data_alerts(self):
        """检测无数据告警

        Returns:
            list: 无数据事件列表
        """
        if not self.policy.no_data_period or not self.policy.source:
            return []

        aggregation_metrics = self.metric_query_service.query_aggregation_metrics(
            self.policy.no_data_period
        )
        aggregation_result = self.metric_query_service.format_aggregation_metrics(
            aggregation_metrics
        )

        events = self._build_no_data_events(aggregation_result)

        if events:
            self._log_no_data_events(events, aggregation_metrics)

        return events

    def _filter_events_by_instance_scope(self, events):
        """根据实例范围过滤事件"""
        return [
            event
            for event in events
            if event["instance_id"] in self.instances_map.keys()
        ]

    def _build_no_data_events(self, aggregation_result):
        """构建无数据事件列表"""
        events = []
        no_data_alert_name = self.policy.no_data_alert_name or "no data"
        monitor_object_name = (
            self.policy.monitor_object.name if self.policy.monitor_object else ""
        )
        metric_name = self._get_metric_display_name()
        no_data_level = self.policy.no_data_level or "warning"

        for instance_id in self.instances_map.keys():
            if instance_id not in aggregation_result:
                template_context = {
                    "instance_id": instance_id,
                    "metric_instance_id": instance_id,
                    "monitor_instance_id": instance_id,
                    "instance_name": self.instances_map.get(instance_id, instance_id),
                    "monitor_object": monitor_object_name,
                    "metric_name": metric_name,
                    "level": no_data_level,
                    "value": "",
                }

                template = Template(no_data_alert_name)
                content = template.safe_substitute(template_context)

                events.append(
                    {
                        "instance_id": instance_id,
                        "value": None,
                        "level": "no_data",
                        "content": content,
                    }
                )
        return events

    def _log_alert_events(self, alert_events, vm_data):
        """记录告警事件日志"""
        logger.info(f"=======alert events: {alert_events}")
        logger.info(f"=======alert events search result: {vm_data}")
        logger.info(f"=======alert events resource scope: {self.instances_map.keys()}")

    def _log_no_data_events(self, events, aggregation_metrics):
        """记录无数据事件日志"""
        logger.info(f"-------no data events: {events}")
        logger.info(f"-------no data events search result: {aggregation_metrics}")
        logger.info(
            f"-------no data events resource scope: {self.instances_map.keys()}"
        )

    def count_events(self, alert_events, info_events):
        """统计告警和正常事件,更新告警计数器"""
        alerts_map = {
            alert.monitor_instance_id: alert.id
            for alert in self.active_alerts
            if alert.alert_type == "alert"
        }

        info_alert_ids = {
            alerts_map[event["instance_id"]]
            for event in info_events
            if event["instance_id"] in alerts_map
        }

        alert_alert_ids = {
            alerts_map[event["instance_id"]]
            for event in alert_events
            if event["instance_id"] in alerts_map
        }

        self._increment_info_count(info_alert_ids)
        self._clear_info_count(alert_alert_ids)

    def _clear_info_count(self, alert_ids):
        """清零告警的正常事件计数"""
        if not alert_ids:
            return
        MonitorAlert.objects.filter(id__in=list(alert_ids)).update(info_event_count=0)

    def _increment_info_count(self, alert_ids):
        """递增告警的正常事件计数"""
        if not alert_ids:
            return
        MonitorAlert.objects.filter(id__in=list(alert_ids)).update(
            info_event_count=F("info_event_count") + 1
        )

    def recover_threshold_alerts(self):
        """处理阈值告警恢复"""
        if self.policy.recovery_condition <= 0:
            return

        alert_ids = [
            alert.id for alert in self.active_alerts if alert.alert_type == "alert"
        ]

        MonitorAlert.objects.filter(
            id__in=alert_ids, info_event_count__gte=self.policy.recovery_condition
        ).update(
            status="recovered",
            end_event_time=self.policy.last_run_time,
            operator="system",
        )

    def recover_no_data_alerts(self):
        """处理无数据告警恢复"""
        if not self.policy.no_data_recovery_period:
            return

        aggregation_metrics = self.metric_query_service.query_aggregation_metrics(
            self.policy.no_data_recovery_period
        )
        aggregation_result = self.metric_query_service.format_aggregation_metrics(
            aggregation_metrics
        )

        instance_ids = set(aggregation_result.keys())

        MonitorAlert.objects.filter(
            policy_id=self.policy.id,
            monitor_instance_id__in=instance_ids,
            alert_type="no_data",
            status="new",
        ).update(
            status="recovered",
            end_event_time=self.policy.last_run_time,
            operator="system",
        )
