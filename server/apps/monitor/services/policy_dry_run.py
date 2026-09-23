"""策略预检：只读复用扫描判定，不落告警 / 事件 / 快照 / 通知。"""

from django.utils import timezone
from rest_framework.exceptions import ValidationError as DrfValidationError

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.models import MonitorAlert, MonitorInstance
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.tasks.services.policy_scan.alert_detector import AlertDetector
from apps.monitor.tasks.services.policy_scan.metric_query import MetricQueryService
from apps.monitor.tasks.services.policy_scan.scanner import MonitorPolicyScan
from apps.monitor.tasks.utils.policy_calculate import _parse_finite_float
from apps.monitor.tasks.utils.policy_methods import COMPARE_MODE_ABSOLUTE
from apps.monitor.utils.dimension import parse_instance_id
from apps.monitor.utils.unit_converter import UnitConverter

DRY_RUN_INSTANCE_LIMIT = 200
DRY_RUN_FAIL_TEMPLATE = (
    "event=monitor_policy_dry_run_failed policy_id=%s failed_stage=%s error_type=%s"
)
HIT_COUNT_REASON = "本轮命中 {hit}/{total}，现网不会建告警"
MISSING_BASELINE_REASON = "对照缺失或留存不足"
NO_DATA_REASON = "无数据"
INSUFFICIENT_SAMPLES_REASON = "样本不足"
TRUNCATED_WARNING = f"实例超过 {DRY_RUN_INSTANCE_LIMIT}，已截断"

_SKIP_POLICY_FIELDS = frozenset({"id", "last_run_time"})


def _raise_for_vm_error(data):
    if not isinstance(data, dict) or data.get("status") in (None, "success"):
        return
    raise BaseAppException("预检失败")


class PolicyDryRunService:
    def __init__(self, payload, actor_context):
        self.payload = payload or {}
        self.actor_context = actor_context

    def run(self):
        failed_stage = "serialize"
        policy_id = ""
        try:
            policy_id, preview, policy = self._build_unsaved_policy()
            failed_stage = "authorize_instances"
            instances_map, truncated = self._authorized_instances(policy, preview)
            failed_stage = "query_existence"
            metric_query = MetricQueryService(policy, instances_map)
            metric_query.set_monitor_obj_instance_key()
            existence_data = metric_query.query_existence_metrics(policy.period)
            _raise_for_vm_error(existence_data)
            failed_stage = "query_comparison"
            trigger_count = max(1, int(getattr(policy, "trigger_count", 1) or 1))
            comparison_data = metric_query.query_comparison_metrics(
                policy.period, trigger_count
            )
            _raise_for_vm_error(comparison_data)
            comparison_data = metric_query.convert_metric_values(comparison_data)
            failed_stage = "query_overlay"
            current_map, baseline_map = self._overlay_value_maps(
                policy, metric_query
            )
            failed_stage = "classify"
            items = self._classify(
                policy,
                policy_id,
                instances_map,
                metric_query,
                existence_data,
                comparison_data,
                current_map,
                baseline_map,
                trigger_count,
            )
            warnings = [TRUNCATED_WARNING] if truncated else []
            return {
                "items": items,
                "truncated": truncated,
                "warnings": warnings,
            }
        except (UnauthorizedException, DrfValidationError):
            raise
        except Exception as exc:
            logger.warning(
                DRY_RUN_FAIL_TEMPLATE,
                policy_id or "",
                failed_stage,
                type(exc).__name__,
                exc_info=True,
            )
            raise BaseAppException("预检失败") from exc

    @classmethod
    def authorize_preview_payload(cls, payload, actor_context):
        preview = (payload or {}).get("preview") or {}
        instance_id = preview.get("instance_id")
        if not instance_id:
            return
        object_id = payload.get("monitor_object") or payload.get("monitor_object_id")
        if object_id in (None, ""):
            raise UnauthorizedException("无权限访问指定监控资产")
        expanded = MonitorPolicyScan._expand_instance_source_values([instance_id])
        authorized = cls._authorized_id_set(actor_context, object_id, expanded)
        matched = next((item for item in expanded if item in authorized), None)
        if not matched:
            raise UnauthorizedException("无权限访问指定监控资产")
        parsed = parse_instance_id(matched)
        if parsed:
            preview = dict(preview)
            preview["instance_id"] = matched
            preview["instance_id_values"] = [str(value) for value in parsed]
            payload["preview"] = preview

    def _build_unsaved_policy(self):
        payload = dict(self.payload)
        preview = payload.pop("preview", None) or {}
        raw_policy_id = payload.pop("id", None)
        serializer = MonitorPolicySerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        last_run_time = timezone.now()
        policy = MonitorPolicy()
        for field in MonitorPolicy._meta.concrete_fields:
            name = field.name
            if name in _SKIP_POLICY_FIELDS:
                continue
            if name in serializer.validated_data:
                setattr(policy, name, serializer.validated_data[name])
        policy.last_run_time = last_run_time
        saved_id = self._visible_saved_policy_id(raw_policy_id)
        return saved_id, preview, policy

    def _visible_saved_policy_id(self, raw_policy_id):
        if raw_policy_id in (None, ""):
            return ""
        try:
            saved_id = int(raw_policy_id)
        except (TypeError, ValueError):
            return ""
        qs = MonitorPolicy.objects.filter(pk=saved_id)
        if not qs.exists():
            return ""
        actor = self.actor_context or {}
        if actor.get("is_superuser"):
            return saved_id
        data_scope = actor.get("data_scope")
        team_ids = list(getattr(data_scope, "data_team_ids", None) or [])
        if not team_ids:
            return ""
        if qs.filter(policyorganization__organization__in=team_ids).exists():
            return saved_id
        return ""

    @classmethod
    def _authorized_id_set(cls, actor_context, object_id, candidate_ids):
        if not actor_context:
            raise UnauthorizedException("无权限访问指定监控资产")
        normalized = [str(item) for item in candidate_ids if item not in (None, "")]
        if not normalized:
            return set()
        return {
            str(instance_id)
            for instance_id in InstanceConfigService._get_authorized_monitor_instances(
                actor_context,
                object_id,
                require_operate=False,
            )
            .filter(id__in=normalized, is_deleted=False)
            .values_list("id", flat=True)
        }

    def _authorized_instances(self, policy, preview):
        source = policy.source or {}
        source_type = source.get("type")
        source_values = source.get("values") or []
        scan = MonitorPolicyScan.__new__(MonitorPolicyScan)
        scan.policy = policy
        candidate_ids = scan._get_instance_list_by_source(source_type, source_values)
        preview_id = preview.get("instance_id")
        preview_expanded = (
            MonitorPolicyScan._expand_instance_source_values([preview_id])
            if preview_id
            else []
        )
        lookup_ids = list(dict.fromkeys([*preview_expanded, *candidate_ids]))
        authorized = self._authorized_id_set(
            self.actor_context, policy.monitor_object_id, lookup_ids
        )
        if preview_expanded and not any(item in authorized for item in preview_expanded):
            raise UnauthorizedException("无权限访问指定监控资产")
        ordered = []
        for item in preview_expanded:
            if item in authorized and item not in ordered:
                ordered.append(item)
        for item in candidate_ids:
            if item in authorized and item not in ordered:
                ordered.append(item)
        truncated = len(ordered) > DRY_RUN_INSTANCE_LIMIT
        if truncated:
            ordered = ordered[:DRY_RUN_INSTANCE_LIMIT]
        instances = MonitorInstance.objects.filter(
            monitor_object_id=policy.monitor_object_id,
            id__in=ordered,
            is_deleted=False,
        ).only("id", "name")
        name_by_id = {instance.id: instance.name for instance in instances}
        instances_map = {
            instance_id: name_by_id.get(instance_id, instance_id)
            for instance_id in ordered
            if instance_id in name_by_id
        }
        return instances_map, truncated

    def _overlay_value_maps(self, policy, metric_query):
        return metric_query.query_overlay_last_values()

    def _classify(
        self,
        policy,
        policy_id,
        instances_map,
        metric_query,
        existence_data,
        comparison_data,
        current_map,
        baseline_map,
        trigger_count,
    ):
        existence_series = self._series_map(existence_data, metric_query, instances_map)
        comparison_series = self._series_map(
            comparison_data, metric_query, instances_map
        )
        alert_events, info_events, hold_events = AlertDetector(
            policy,
            instances_map,
            {},
            [],
            metric_query,
        ).detect_threshold_alerts(log_events=False, vm_data=comparison_data)
        alert_by_metric = {
            event["metric_instance_id"]: event for event in alert_events
        }
        info_by_metric = {event["metric_instance_id"]: event for event in info_events}
        hold_by_metric = {event["metric_instance_id"]: event for event in hold_events}
        active_by_instance = {}
        if policy_id:
            for alert in MonitorAlert.objects.filter(
                policy_id=policy_id, status="new", alert_type="alert"
            ):
                active_by_instance.setdefault(alert.monitor_instance_id, alert)
        converted_thresholds = metric_query.convert_thresholds(policy.threshold or [])
        result_unit = metric_query.get_effective_calculation_unit()
        items = []
        covered_instances = set()

        for metric_instance_id, series in existence_series.items():
            monitor_instance_id = series["monitor_instance_id"]
            covered_instances.add(monitor_instance_id)
            comparison = comparison_series.get(metric_instance_id)
            compared_values = self._numeric_tail(
                (comparison or {}).get("values") or [], trigger_count
            )
            hit_count = self._count_threshold_hits(
                compared_values, converted_thresholds
            )
            current_value = current_map.get(metric_instance_id)
            baseline_value = baseline_map.get(metric_instance_id)
            compared_value = compared_values[-1] if compared_values else None
            if compare_is_absolute(policy) and compared_value is not None:
                current_value = compared_value
            row = {
                "instance_id": monitor_instance_id,
                "instance_name": instances_map.get(
                    monitor_instance_id, monitor_instance_id
                ),
                "metric_instance_id": metric_instance_id,
                "current_value": current_value,
                "baseline_value": baseline_value,
                "compared_value": compared_value,
                "result_unit": result_unit,
                "result_unit_display": (
                    UnitConverter.get_display_unit(result_unit) if result_unit else ""
                ),
                "matched_threshold": None,
                "hit_count": hit_count,
                "trigger_count": trigger_count,
            }
            if comparison is None:
                row.update(
                    verdict="missing_baseline",
                    reason=MISSING_BASELINE_REASON,
                )
            elif len(compared_values) < trigger_count:
                row.update(
                    verdict="insufficient_samples",
                    reason=self._hit_reason(
                        hit_count, trigger_count, INSUFFICIENT_SAMPLES_REASON
                    ),
                )
            elif metric_instance_id in alert_by_metric:
                event = alert_by_metric[metric_instance_id]
                row["compared_value"] = event.get("value", compared_value)
                row["matched_threshold"] = self._matched_threshold(
                    converted_thresholds, event.get("level")
                )
                row.update(verdict="would_trigger", reason="")
            elif metric_instance_id in hold_by_metric:
                event = hold_by_metric[metric_instance_id]
                row["compared_value"] = self._event_numeric(event, compared_value)
                recover_alert = active_by_instance.get(monitor_instance_id)
                if recover_alert:
                    row.update(verdict="hold", reason="")
                else:
                    row.update(
                        verdict="ok",
                        reason=self._hit_reason(hit_count, trigger_count, ""),
                    )
            elif metric_instance_id in info_by_metric:
                event = info_by_metric[metric_instance_id]
                row["compared_value"] = self._event_numeric(event, compared_value)
                recover_alert = active_by_instance.get(monitor_instance_id)
                if recover_alert and self._would_recover(policy, recover_alert):
                    row.update(verdict="would_recover", reason="")
                else:
                    row.update(
                        verdict="ok",
                        reason=self._hit_reason(hit_count, trigger_count, ""),
                    )
            else:
                row.update(
                    verdict="insufficient_samples",
                    reason=self._hit_reason(
                        hit_count, trigger_count, INSUFFICIENT_SAMPLES_REASON
                    ),
                )
            items.append(row)

        for instance_id, instance_name in instances_map.items():
            if instance_id in covered_instances:
                continue
            items.append(
                {
                    "instance_id": instance_id,
                    "instance_name": instance_name,
                    "metric_instance_id": instance_id,
                    "verdict": "no_data",
                    "current_value": None,
                    "baseline_value": None,
                    "compared_value": None,
                    "result_unit": result_unit,
                    "result_unit_display": (
                        UnitConverter.get_display_unit(result_unit)
                        if result_unit
                        else ""
                    ),
                    "matched_threshold": None,
                    "reason": NO_DATA_REASON,
                    "hit_count": 0,
                    "trigger_count": trigger_count,
                }
            )

        return self._sort_items(items, list(instances_map.keys()))

    @staticmethod
    def _would_recover(policy, alert):
        recovery_condition = int(getattr(policy, "recovery_condition", 0) or 0)
        if recovery_condition <= 0:
            return False
        return int(alert.info_event_count or 0) + 1 >= recovery_condition

    @staticmethod
    def _hit_reason(hit_count, trigger_count, prefix):
        if trigger_count > 1 and hit_count < trigger_count:
            copy = HIT_COUNT_REASON.format(hit=hit_count, total=trigger_count)
            if prefix:
                return f"{prefix}；{copy}"
            return copy
        return prefix

    @staticmethod
    def _matched_threshold(thresholds, level):
        for item in thresholds or []:
            if item.get("level") == level:
                return {
                    "method": item.get("method"),
                    "value": item.get("value"),
                    "level": item.get("level"),
                }
        return None

    @staticmethod
    def _event_numeric(event, fallback):
        parsed = _parse_finite_float(event.get("value"))
        return fallback if parsed is None else parsed

    @staticmethod
    def _numeric_tail(values, trigger_count):
        tail = list(values or [])[-max(1, trigger_count) :]
        numbers = []
        for point in tail:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            parsed = _parse_finite_float(point[1])
            if parsed is not None:
                numbers.append(parsed)
        return numbers

    @staticmethod
    def _count_threshold_hits(numeric_values, thresholds):
        checks = []
        for item in thresholds or []:
            method = AlertConstants.THRESHOLD_METHODS.get(item.get("method"))
            if method is None:
                continue
            checks.append((method, item.get("value")))
        if not checks:
            return 0
        hits = 0
        for value in numeric_values:
            if any(method(value, threshold) for method, threshold in checks):
                hits += 1
        return hits

    def _series_map(self, vm_data, metric_query, instances_map):
        series = {}
        group_by_keys = metric_query.get_result_group_by()
        for metric_info in (vm_data or {}).get("data", {}).get("result", []) or []:
            labels = metric_info.get("metric") or {}
            instance_id_tuple = tuple(labels.get(key) for key in group_by_keys)
            metric_instance_id = str(instance_id_tuple)
            monitor_instance_id = metric_query.get_monitor_instance_id_from_tuple(
                instance_id_tuple, group_by_keys
            )
            if instances_map and monitor_instance_id not in instances_map:
                continue
            series[metric_instance_id] = {
                "monitor_instance_id": monitor_instance_id or metric_instance_id,
                "values": metric_info.get("values") or [],
            }
        return series

    @staticmethod
    def _sort_items(items, instance_order):
        rank = {instance_id: index for index, instance_id in enumerate(instance_order)}
        return sorted(
            items,
            key=lambda item: (
                rank.get(item.get("instance_id"), len(rank)),
                item.get("metric_instance_id") or "",
            ),
        )


def compare_is_absolute(policy):
    mode = getattr(policy, "compare_mode", None) or COMPARE_MODE_ABSOLUTE
    return mode in ("", COMPARE_MODE_ABSOLUTE)
