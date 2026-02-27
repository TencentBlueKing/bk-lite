"""告警检测服务 - 负责告警事件的检测和恢复"""

from string import Template

from django.db.models import F

from apps.monitor.models import MonitorAlert
from apps.monitor.tasks.utils.policy_calculate import vm_to_dataframe, calculate_alerts
from apps.monitor.utils.dimension import (
    build_dimensions,
    extract_monitor_instance_id,
    format_dimension_str,
    format_dimension_value,
    build_metric_template_vars,
)
from apps.core.logger import celery_logger as logger


class AlertDetector:
    def __init__(
        self,
        policy,
        instances_map: dict,
        baselines_map: dict,
        active_alerts,
        metric_query_service,
    ):
        self.policy = policy
        self.instances_map = instances_map
        self.baselines_map = baselines_map
        self.active_alerts = active_alerts
        self.metric_query_service = metric_query_service

    def detect_threshold_alerts(self):
        vm_data = self.metric_query_service.query_aggregation_metrics(
            self.policy.period
        )
        vm_data = self.metric_query_service.convert_metric_values(vm_data)

        group_by_keys = self.policy.group_by or []
        df = vm_to_dataframe(
            vm_data.get("data", {}).get("result", []),
            group_by_keys,
        )

        template_context = {
            "monitor_object": self.policy.monitor_object.name
            if self.policy.monitor_object
            else "",
            "metric_name": self._get_metric_display_name(),
            "instances_map": self.instances_map,
            "instance_id_keys": group_by_keys,
            "dimension_name_map": self._build_dimension_name_map(),
            "display_unit": self.metric_query_service.get_display_unit(),
            "enum_value_map": self.metric_query_service.get_enum_value_map(),
        }

        alert_events, info_events = calculate_alerts(
            self.policy.alert_name, df, self.policy.threshold, template_context
        )

        if self.policy.source:
            alert_events = self._filter_events_by_scope(alert_events)
            info_events = self._filter_events_by_scope(info_events)

        if alert_events:
            self._log_alert_events(alert_events, vm_data)

        return alert_events, info_events

    def _get_metric_display_name(self):
        metric = self.metric_query_service.metric
        if metric:
            return metric.display_name or metric.name
        return self.policy.query_condition.get("metric_id", "")

    def detect_no_data_alerts(self):
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

    def _filter_events_by_scope(self, events):
        return [
            e
            for e in events
            if self._extract_monitor_instance_id(e["metric_instance_id"])
            in self.instances_map
        ]

    def _extract_monitor_instance_id(self, metric_instance_id: str) -> str:
        return extract_monitor_instance_id(metric_instance_id)

    def _build_no_data_events(self, aggregation_result):
        events = []
        no_data_alert_name = self.policy.no_data_alert_name or "no data"
        monitor_object_name = (
            self.policy.monitor_object.name if self.policy.monitor_object else ""
        )
        metric_name = self._get_metric_display_name()
        no_data_level = self.policy.no_data_level or "warning"

        baseline_keys = set(self.baselines_map.keys()) if self.baselines_map else set()
        if not baseline_keys:
            baseline_keys = set(self.instances_map.keys())

        for metric_instance_id in baseline_keys:
            if metric_instance_id in aggregation_result:
                continue

            monitor_instance_id = self.baselines_map.get(
                metric_instance_id
            ) or self._extract_monitor_instance_id(metric_instance_id)
            resource_name = self.instances_map.get(
                monitor_instance_id, monitor_instance_id
            )
            dimensions = self._parse_dimensions(metric_instance_id)
            dimension_str = self._format_dimension_str(dimensions)
            display_name = (
                f"{resource_name} - {dimension_str}" if dimension_str else resource_name
            )
            dimension_value = format_dimension_value(
                dimensions,
                ordered_keys=self.policy.group_by or [],
                name_map=self._build_dimension_name_map(),
            )

            template_context = {
                "metric_instance_id": metric_instance_id,
                "monitor_instance_id": monitor_instance_id,
                "instance_name": display_name,
                "resource_name": resource_name,
                "monitor_object": monitor_object_name,
                "metric_name": metric_name,
                "level": no_data_level,
                "value": "",
                "dimension_value": dimension_value,
            }
            template_context.update(self._build_metric_template_vars(dimensions))

            template = Template(no_data_alert_name)
            content = template.safe_substitute(template_context)

            events.append(
                {
                    "metric_instance_id": metric_instance_id,
                    "monitor_instance_id": monitor_instance_id,
                    "dimensions": dimensions,
                    "value": None,
                    "level": "no_data",
                    "content": content,
                }
            )
        return events

    def _parse_dimensions(self, metric_instance_id: str) -> dict:
        keys = self.policy.group_by or []
        return build_dimensions(metric_instance_id, keys)

    def _format_dimension_str(self, dimensions: dict) -> str:
        return format_dimension_str(dimensions)

    def _build_metric_template_vars(self, dimensions: dict) -> dict:
        return build_metric_template_vars(dimensions)

    def _build_dimension_name_map(self) -> dict:
        metric = self.metric_query_service.metric
        if not metric:
            return {}

        name_map = {}
        for item in metric.dimensions or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            display_name = item.get("display_name") or item.get("description") or name
            name_map[name] = display_name

        return name_map

    def _log_alert_events(self, alert_events, vm_data):
        logger.info(f"=======alert events: {alert_events}")
        logger.info(f"=======alert events search result: {vm_data}")
        logger.info(f"=======alert events resource scope: {self.instances_map.keys()}")

    def _log_no_data_events(self, events, aggregation_metrics):
        logger.info(f"-------no data events: {events}")
        logger.info(f"-------no data events search result: {aggregation_metrics}")
        logger.info(
            f"-------no data events resource scope: {self.instances_map.keys()}"
        )

    def count_events(self, alert_events, info_events):
        alerts_map = {
            self._get_alert_metric_instance_id(alert): alert.id
            for alert in self.active_alerts
            if alert.alert_type == "alert"
        }

        info_alert_ids = {
            alerts_map[event["metric_instance_id"]]
            for event in info_events
            if event["metric_instance_id"] in alerts_map
        }

        alert_alert_ids = {
            alerts_map[event["metric_instance_id"]]
            for event in alert_events
            if event["metric_instance_id"] in alerts_map
        }

        self._increment_info_count(info_alert_ids)
        self._clear_info_count(alert_alert_ids)

    def _get_alert_metric_instance_id(self, alert) -> str:
        if alert.metric_instance_id:
            return alert.metric_instance_id
        return str((alert.monitor_instance_id,))

    def _clear_info_count(self, alert_ids):
        if not alert_ids:
            return
        MonitorAlert.objects.filter(id__in=list(alert_ids)).update(info_event_count=0)

    def _increment_info_count(self, alert_ids):
        if not alert_ids:
            return
        MonitorAlert.objects.filter(id__in=list(alert_ids)).update(
            info_event_count=F("info_event_count") + 1
        )

    def recover_threshold_alerts(self):
        if self.policy.recovery_condition <= 0:
            return

        alert_ids = [
            alert.id for alert in self.active_alerts if alert.alert_type == "alert"
        ]

        alerts_to_recover = list(
            MonitorAlert.objects.filter(
                id__in=alert_ids, info_event_count__gte=self.policy.recovery_condition
            )
        )
        if not alerts_to_recover:
            return

        end_time = self.policy.last_run_time
        operation_log = {
            "action": "recovered",
            "reason": "auto_recovered",
            "operator": "system",
            "time": end_time.isoformat() if end_time else None,
        }
        for alert in alerts_to_recover:
            alert.status = "recovered"
            alert.end_event_time = end_time
            alert.operator = "system"
            alert.operation_logs = (alert.operation_logs or []) + [operation_log]
        MonitorAlert.objects.bulk_update(
            alerts_to_recover,
            fields=["status", "end_event_time", "operator", "operation_logs"],
        )

    def recover_no_data_alerts(self):
        if not self.policy.no_data_recovery_period:
            logger.debug(
                f"Policy {self.policy.id}: no_data_recovery_period not configured, skip recovery"
            )
            return

        aggregation_metrics = self.metric_query_service.query_aggregation_metrics(
            self.policy.no_data_recovery_period
        )
        logger.debug(
            f"Policy {self.policy.id}: no_data recovery query returned "
            f"{len(aggregation_metrics.get('data', {}).get('result', []))} results"
        )

        aggregation_result = self.metric_query_service.format_aggregation_metrics(
            aggregation_metrics
        )

        metric_instance_ids_with_data = set(aggregation_result.keys())
        logger.debug(
            f"Policy {self.policy.id}: metric_instance_ids_with_data = {metric_instance_ids_with_data}"
        )

        no_data_alerts = [
            alert for alert in self.active_alerts if alert.alert_type == "no_data"
        ]
        logger.debug(
            f"Policy {self.policy.id}: found {len(no_data_alerts)} active no_data alerts"
        )

        alerts_to_recover = []
        for alert in no_data_alerts:
            alert_metric_id = self._get_alert_metric_instance_id(alert)
            logger.debug(
                f"Policy {self.policy.id}: alert {alert.id} metric_id={alert_metric_id}, "
                f"in_data_set={alert_metric_id in metric_instance_ids_with_data}"
            )
            if alert_metric_id in metric_instance_ids_with_data:
                alerts_to_recover.append(alert)

        if alerts_to_recover:
            end_time = self.policy.last_run_time
            operation_log = {
                "action": "recovered",
                "reason": "auto_recovered",
                "operator": "system",
                "time": end_time.isoformat() if end_time else None,
            }
            for alert in alerts_to_recover:
                alert.status = "recovered"
                alert.end_event_time = end_time
                alert.operator = "system"
                alert.operation_logs = (alert.operation_logs or []) + [operation_log]
            MonitorAlert.objects.bulk_update(
                alerts_to_recover,
                fields=["status", "end_event_time", "operator", "operation_logs"],
            )
            logger.info(
                f"Policy {self.policy.id}: recovered {len(alerts_to_recover)} no_data alerts"
            )
        else:
            logger.debug(f"Policy {self.policy.id}: no no_data alerts to recover")
