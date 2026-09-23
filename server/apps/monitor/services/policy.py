import copy
import hashlib
import io
import json
import re
import uuid
import zipfile
from pathlib import PurePosixPath

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import MonitorAlert, MonitorEvent, MonitorObject, MonitorPlugin, MonitorPolicy, PolicyTemplate
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.services.alert_lifecycle_events import record_lifecycle_events
from apps.monitor.services.alert_lifecycle_notify import NOTIFY_SCOPE_ALERT_CENTER_ONLY, AlertLifecycleNotifier
from apps.monitor.services.policy_bulk import normalize_default_calculation_unit, normalize_stored_metric_unit, normalize_template_algorithms

ARCHIVE_FORMAT = "bk-lite-monitor-policy-templates"
ARCHIVE_SCHEMA_VERSION = 1
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_FILES = 100
MAX_ARCHIVE_TEMPLATES = MAX_ARCHIVE_FILES - 1
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_TEMPLATE_BYTES = 2 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
POLICY_RECIPE_SYNC_FIELDS = (
    "alert_name",
    "query_condition",
    "threshold",
    "group_algorithm",
    "algorithm",
    "group_by",
    "metric_unit",
    "calculation_unit",
    "threshold_unit",
    "compare_mode",
    "compare_value_kind",
    "compare_offset_hours",
    "compare_offset_days",
    "compare_baseline_weeks",
    "count_predicate",
    "forecast_target",
    "forecast_target_unit",
    "forecast_lookback",
    "recovery_threshold",
)


class PolicyService:
    """策略模板模块。

    同一个 Interface 隐藏内置初始化、自定义模板、可移植配置及 ZIP 格式细节。
    """

    @staticmethod
    def build_builtin_key(object_name, plugin_name, template):
        explicit_key = str(template.get("key") or "").strip()
        identity = explicit_key or str(template.get("name") or template.get("alert_name") or template.get("metric_name") or "").strip()
        if not identity:
            raise BaseAppException("内置策略模板缺少 name")
        digest = hashlib.sha256(f"{object_name}\0{plugin_name}\0{identity}".encode("utf-8")).hexdigest()[:24]
        return f"builtin:{digest}"

    @staticmethod
    def _extract_builtin_pair(data):
        if not isinstance(data, dict):
            raise BaseAppException("policy.json 必须是对象")
        object_name = str(data.get("object") or "").strip()
        plugin_name = str(data.get("plugin") or "").strip()
        if not object_name or not plugin_name:
            raise BaseAppException("policy.json 缺少 object 或 plugin")
        return object_name, plugin_name

    @staticmethod
    def _normalize_builtin_documents(documents):
        normalized = []
        seen_pairs = set()
        seen_keys = set()
        for data in documents:
            object_name, plugin_name = PolicyService._extract_builtin_pair(data)
            pair = (object_name, plugin_name)
            if pair in seen_pairs:
                raise BaseAppException(f"内置策略模板重复定义: {object_name}/{plugin_name}")
            seen_pairs.add(pair)
            templates = data.get("templates")
            if not isinstance(templates, list):
                raise BaseAppException(f"{object_name}/{plugin_name} 的 templates 必须是列表")
            pair_keys = set()
            for raw_template in templates:
                if not isinstance(raw_template, dict):
                    raise BaseAppException(f"{object_name}/{plugin_name} 包含非法模板")
                name = str(raw_template.get("name") or raw_template.get("alert_name") or raw_template.get("metric_name") or "").strip()
                if not name:
                    raise BaseAppException(f"{object_name}/{plugin_name} 的模板缺少 name")
                key = PolicyService.build_builtin_key(object_name, plugin_name, raw_template)
                if key in pair_keys or key in seen_keys:
                    raise BaseAppException(f"内置策略模板 key 重复: {key}")
                pair_keys.add(key)
                seen_keys.add(key)
                config = copy.deepcopy(raw_template)
                config.pop("key", None)
                config.pop("name", None)
                description = str(config.pop("description", "") or "")
                if "threshold" in config and not isinstance(config["threshold"], list):
                    config["threshold"] = [
                        {
                            "level": config.pop("level", "warning"),
                            "method": config.pop("method", ">"),
                            "value": config["threshold"],
                        }
                    ]
                if str(config.get("algorithm") or "").lower() == "threshold":
                    config["group_algorithm"] = "avg"
                    config["algorithm"] = "avg_over_time"
                normalized.append(
                    {
                        "key": key,
                        "object_name": object_name,
                        "plugin_name": plugin_name,
                        "name": name,
                        "description": description,
                        "config": config,
                    }
                )
        return normalized

    @staticmethod
    def sync_builtin_policy_templates(documents):
        normalized = PolicyService._normalize_builtin_documents(documents)
        object_names = {item["object_name"] for item in normalized}
        plugin_names = {item["plugin_name"] for item in normalized}
        objects = {item.name: item for item in MonitorObject.objects.filter(name__in=object_names)}
        plugins = {item.name: item for item in MonitorPlugin.objects.filter(name__in=plugin_names)}
        missing_objects = sorted(object_names - objects.keys())
        missing_plugins = sorted(plugin_names - plugins.keys())
        if missing_objects:
            raise BaseAppException(f"监控对象不存在: {', '.join(missing_objects)}")
        if missing_plugins:
            raise BaseAppException(f"监控插件不存在: {', '.join(missing_plugins)}")

        expected_keys = {item["key"] for item in normalized}
        existing = {
            template.key: template
            for template in PolicyTemplate.objects.filter(
                template_type=PolicyTemplate.TYPE_BUILTIN,
                scope_key=PolicyTemplate.TYPE_BUILTIN,
            )
        }
        now = timezone.now()
        to_create = []
        to_update = []
        with transaction.atomic():
            for item in normalized:
                monitor_object = objects[item["object_name"]]
                plugin = plugins[item["plugin_name"]]
                current = existing.get(item["key"])
                if current is None:
                    to_create.append(
                        PolicyTemplate(
                            scope_key=PolicyTemplate.TYPE_BUILTIN,
                            key=item["key"],
                            template_type=PolicyTemplate.TYPE_BUILTIN,
                            organization=None,
                            monitor_object=monitor_object,
                            plugin=plugin,
                            name=item["name"],
                            description=item["description"],
                            config=item["config"],
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    continue
                if not PolicyService._builtin_template_changed(current, item, monitor_object, plugin):
                    continue
                current.monitor_object = monitor_object
                current.plugin = plugin
                current.name = item["name"]
                current.description = item["description"]
                current.config = item["config"]
                current.updated_at = now
                to_update.append(current)
            if to_create:
                PolicyTemplate.objects.bulk_create(to_create, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
            if to_update:
                PolicyTemplate.objects.bulk_update(
                    to_update,
                    ["name", "description", "config", "monitor_object", "plugin"],
                    batch_size=DatabaseConstants.BULK_UPDATE_BATCH_SIZE,
                )
            stale_ids = [template.id for template in existing.values() if template.key not in expected_keys]
            deleted_count = 0
            if stale_ids:
                deleted_count, _ = PolicyTemplate.objects.filter(id__in=stale_ids).delete()
        return {
            "created_count": len(to_create),
            "updated_count": len(to_update),
            "deleted_count": deleted_count,
        }

    @staticmethod
    def _builtin_template_changed(template, item, monitor_object, plugin):
        return (
            template.name != item["name"]
            or template.description != item["description"]
            or template.config != item["config"]
            or template.monitor_object_id != monitor_object.id
            or template.plugin_id != plugin.id
        )

    @staticmethod
    def _upsert_builtin_template(item, monitor_object, plugin):
        return PolicyTemplate.objects.update_or_create(
            scope_key=PolicyTemplate.TYPE_BUILTIN,
            key=item["key"],
            defaults={
                "template_type": PolicyTemplate.TYPE_BUILTIN,
                "organization": None,
                "monitor_object": monitor_object,
                "plugin": plugin,
                "name": item["name"],
                "description": item["description"],
                "config": item["config"],
            },
        )

    @staticmethod
    def import_monitor_policy(data):
        """兼容单文件调用；仅对账该对象和插件下的内置模板。"""
        normalized = PolicyService._normalize_builtin_documents([data])
        object_name = data["object"]
        plugin_name = data["plugin"]
        monitor_object = MonitorObject.objects.get(name=object_name)
        plugin = MonitorPlugin.objects.get(name=plugin_name)
        expected_keys = {item["key"] for item in normalized}
        with transaction.atomic():
            for item in normalized:
                PolicyService._upsert_builtin_template(item, monitor_object, plugin)
            PolicyTemplate.objects.filter(
                template_type=PolicyTemplate.TYPE_BUILTIN,
                monitor_object=monitor_object,
                plugin=plugin,
            ).exclude(key__in=expected_keys).delete()

    @staticmethod
    def _formula_query_ref(index, item):
        raw_ref = str(item.get("ref") or "").strip()
        if raw_ref:
            return raw_ref
        if index < 26:
            return chr(ord("a") + index)
        return f"q{index}"

    @staticmethod
    def _resolve_formula_expression_with_metrics(query):
        expression = str(query.get("expression") or "").strip()
        if not expression:
            return ""
        queries = query.get("queries") or []
        if not isinstance(queries, list):
            return expression
        ref_map = {}
        for index, item in enumerate(queries):
            if not isinstance(item, dict):
                continue
            raw_ref = PolicyService._formula_query_ref(index, item)
            metric_name = str(item.get("metric_name") or "").strip() or raw_ref
            ref_map[raw_ref.lower()] = metric_name
        if not ref_map:
            return expression
        pattern = re.compile(
            r"\b(?:" + "|".join(re.escape(ref) for ref in sorted(ref_map, key=len, reverse=True)) + r")\b",
            re.IGNORECASE,
        )

        def _replace(match):
            return ref_map.get(match.group(0).lower(), match.group(0))

        return pattern.sub(_replace, expression)

    @staticmethod
    def display_metric_name(config):
        config = config or {}
        query = config.get("query_condition") or {}
        if not isinstance(query, dict):
            query = {}
        if query.get("type") == "formula":
            expression = PolicyService._resolve_formula_expression_with_metrics(query)
            result_name = str(query.get("result_name") or "").strip()
            if expression:
                return f"{result_name}（{expression}）" if result_name else expression
            names = []
            for item in query.get("queries") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("metric_name") or "").strip()
                if name:
                    names.append(name)
            if names:
                return " + ".join(names)
            return result_name
        if config.get("metric_name"):
            return str(config["metric_name"]).strip()
        return str(query.get("metric_name") or "").strip()

    @staticmethod
    def serialize_template(template):
        config = copy.deepcopy(template.config or {})
        metric_name = PolicyService.display_metric_name(config)
        return {
            **config,
            "id": template.id,
            "key": template.key,
            "template_key": f"{template.template_type}:{template.id}",
            "template_type": template.template_type,
            "deletable": template.template_type == PolicyTemplate.TYPE_CUSTOM,
            "name": template.name,
            "description": template.description or "--",
            "metric_name": metric_name,
            "trigger_count": config.get("trigger_count", 1),
            "monitor_object_id": template.monitor_object_id,
            "monitor_object_name": template.monitor_object.name,
            "monitor_object_display_name": template.monitor_object.display_name or template.monitor_object.name,
            "plugin_id": template.plugin_id,
            "plugin_name": template.plugin.name,
            "plugin_display_name": template.plugin.display_name or template.plugin.name,
            "plugin_collector": template.plugin.collector,
            "template_group": (
                f"{template.monitor_object.display_name or template.monitor_object.name}" f"（{template.plugin.display_name or template.plugin.name}）"
            ),
            "related_policy_count": PolicyService._related_policy_count(template),
        }

    @staticmethod
    def get_policy_templates(monitor_object_name, organization=None, plugin_id=None):
        query = (
            PolicyTemplate.objects.select_related("monitor_object", "plugin")
            .annotate(related_policy_count=Count("issued_policies"))
            .filter(monitor_object__name=monitor_object_name)
        )
        if plugin_id not in (None, ""):
            try:
                query = query.filter(plugin_id=int(plugin_id))
            except (TypeError, ValueError):
                return []
        if organization is None:
            query = query.filter(template_type=PolicyTemplate.TYPE_BUILTIN)
        else:
            query = query.filter(
                Q(template_type=PolicyTemplate.TYPE_BUILTIN) | Q(template_type=PolicyTemplate.TYPE_CUSTOM, organization=organization)
            )
        return [PolicyService.serialize_template(item) for item in query.order_by("plugin__name", "name", "id")]

    @staticmethod
    def get_policy_templates_monitor_object(organization=None):
        query = PolicyTemplate.objects.all()
        if organization is None:
            query = query.filter(template_type=PolicyTemplate.TYPE_BUILTIN)
        else:
            query = query.filter(
                Q(template_type=PolicyTemplate.TYPE_BUILTIN) | Q(template_type=PolicyTemplate.TYPE_CUSTOM, organization=organization)
            )
        return list(query.values_list("monitor_object_id", flat=True).distinct())

    @staticmethod
    def _portable_query_condition(query_condition):
        query = copy.deepcopy(query_condition or {})
        metric_ids = []
        if query.get("type") == "formula":
            metric_ids = [item.get("metric_id") for item in query.get("queries") or []]
        elif query.get("metric_id"):
            metric_ids = [query.get("metric_id")]
        metrics = {item.id: item for item in Metric.objects.select_related("monitor_plugin").filter(id__in=metric_ids)}
        if len(metrics) != len(set(metric_ids)):
            raise BaseAppException("模板引用的指标不存在")

        def replace(item):
            metric_id = item.pop("metric_id", None)
            if metric_id:
                metric = metrics[metric_id]
                item["metric_name"] = metric.name
                if metric.monitor_plugin:
                    item["metric_plugin"] = metric.monitor_plugin.name

        if query.get("type") == "formula":
            for item in query.get("queries") or []:
                replace(item)
        else:
            replace(query)
        return query

    @staticmethod
    def _plugin_from_template_payload(template):
        plugin_id = template.get("collect_type") or template.get("plugin_id")
        if plugin_id not in (None, ""):
            plugin = MonitorPlugin.objects.filter(id=plugin_id).first()
            if plugin is not None:
                return plugin
        plugin_name = str(template.get("plugin_name") or "").strip()
        if plugin_name:
            return MonitorPlugin.objects.filter(name=plugin_name).first()
        return None

    @staticmethod
    def _resolve_runtime_metric(monitor_object, metric_name, *, plugin=None, plugin_name=None):
        plugin_name = str(plugin_name or "").strip() or None
        if plugin is not None and plugin_name and plugin_name != plugin.name:
            raise BaseAppException(f"指标插件不匹配: {metric_name}")
        metrics = Metric.objects.filter(monitor_object=monitor_object, name=metric_name)
        if plugin is not None:
            metrics = metrics.filter(monitor_plugin=plugin)
        elif plugin_name:
            metrics = metrics.filter(monitor_plugin__name=plugin_name)
        matches = list(metrics[:2])
        if not matches:
            raise BaseAppException(f"指标不存在: {metric_name}")
        if len(matches) > 1:
            raise BaseAppException(f"指标不唯一: {metric_name}")
        return matches[0]

    @staticmethod
    def _stamp_query_plugin(query, plugin):
        if not isinstance(query, dict) or plugin is None:
            return
        plugin_name = plugin.name
        if query.get("type") == "formula":
            for item in query.get("queries") or []:
                if isinstance(item, dict) and item.get("metric_name") and not item.get("metric_plugin"):
                    item["metric_plugin"] = plugin_name
            return
        if query.get("metric_name") and not query.get("metric_plugin"):
            query["metric_plugin"] = plugin_name

    @staticmethod
    def _runtime_query_condition(query_condition, monitor_object, plugin=None):
        query = copy.deepcopy(query_condition or {})

        def replace(item):
            if not isinstance(item, dict):
                return
            metric_name = item.pop("metric_name", None)
            plugin_name = item.pop("metric_plugin", None)
            if not metric_name:
                return
            metric = PolicyService._resolve_runtime_metric(
                monitor_object,
                metric_name,
                plugin=plugin,
                plugin_name=plugin_name,
            )
            item["metric_id"] = metric.id

        if query.get("type") == "formula":
            for item in query.get("queries") or []:
                replace(item)
        else:
            replace(query)
        return query

    @staticmethod
    def portable_config(config, monitor_object=None, plugin=None):
        portable = copy.deepcopy(config or {})
        for field in (
            "id",
            "key",
            "template_key",
            "template_type",
            "deletable",
            "monitor_object",
            "monitor_object_id",
            "monitor_object_name",
            "organizations",
            "source",
            "collect_type",
            "plugin",
            "plugin_id",
            "plugin_name",
            "notice",
            "notice_type",
            "notice_type_ids",
            "notice_users",
            "enable",
            "last_run_time",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
        ):
            portable.pop(field, None)
        if portable.get("query_condition"):
            portable["query_condition"] = PolicyService._portable_query_condition(portable["query_condition"])
        # 仅补齐稳定指标名；公式展示串不得写入 metric_name，避免导入/回填按 Metric.name 查找失败
        if not portable.get("metric_name"):
            query = portable.get("query_condition") or {}
            if isinstance(query, dict) and query.get("type") != "formula":
                metric_name = str(query.get("metric_name") or "").strip()
                if metric_name:
                    portable["metric_name"] = metric_name
        portable.setdefault("compare_mode", "absolute")
        portable.setdefault("compare_value_kind", "")
        portable.setdefault("compare_offset_hours", None)
        portable.setdefault("compare_offset_days", None)
        portable.setdefault("compare_baseline_weeks", None)
        portable.setdefault("count_predicate", {})
        portable.setdefault("forecast_lookback", {})
        portable.setdefault("recovery_threshold", {})
        portable.setdefault("forecast_target", None)
        portable.setdefault("forecast_target_unit", "")
        portable["schedule"] = PolicyService._default_duration(portable.get("schedule"))
        portable["period"] = PolicyService._default_duration(portable.get("period"))
        PolicyService._ensure_query_condition(portable, plugin=plugin)
        PolicyService._ensure_group_by(portable, monitor_object=monitor_object, plugin=plugin)
        return portable

    @staticmethod
    def _default_duration(value):
        if isinstance(value, dict) and value.get("value") not in (None, ""):
            duration = copy.deepcopy(value)
            duration.setdefault("type", "min")
            return duration
        if isinstance(value, (int, float)) and value > 0:
            return {"type": "min", "value": int(value)}
        return {"type": "min", "value": 5}

    @staticmethod
    def _dimension_names(dimensions):
        names = []
        if not isinstance(dimensions, list):
            return names
        for item in dimensions:
            if isinstance(item, str):
                name = item.strip()
            elif isinstance(item, dict):
                name = str(item.get("name") or "").strip()
            else:
                name = ""
            if name and name not in names:
                names.append(name)
        return names

    @staticmethod
    def _metric_dimension_names(portable, monitor_object=None, plugin=None):
        if monitor_object is None:
            return []
        query = portable.get("query_condition") or {}
        metric_name = str(portable.get("metric_name") or "").strip()
        plugin_name = None
        if isinstance(query, dict):
            if query.get("type") == "formula":
                for item in query.get("queries") or []:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("metric_name") or "").strip()
                    if name:
                        metric_name = name
                        plugin_name = item.get("metric_plugin")
                        break
            else:
                metric_name = metric_name or str(query.get("metric_name") or "").strip()
                plugin_name = query.get("metric_plugin")
        if not metric_name:
            return []
        try:
            metric = PolicyService._resolve_runtime_metric(
                monitor_object,
                metric_name,
                plugin=plugin,
                plugin_name=plugin_name,
            )
        except BaseAppException:
            return []
        return PolicyService._dimension_names(metric.dimensions)

    @staticmethod
    def _ensure_group_by(portable, monitor_object=None, plugin=None):
        existing = portable.get("group_by")
        if isinstance(existing, list):
            cleaned = [str(item).strip() for item in existing if str(item).strip()]
            if cleaned:
                portable["group_by"] = cleaned
                return
        query = portable.get("query_condition") or {}
        if isinstance(query, dict) and query.get("type") == "formula":
            for item in query.get("queries") or []:
                if not isinstance(item, dict):
                    continue
                query_group_by = item.get("group_by")
                if isinstance(query_group_by, list):
                    cleaned = [str(value).strip() for value in query_group_by if str(value).strip()]
                    if cleaned:
                        portable["group_by"] = cleaned
                        return
        fallback = ["instance_id", *PolicyService._metric_dimension_names(portable, monitor_object, plugin)]
        cleaned = []
        seen = set()
        for item in fallback:
            name = str(item).strip()
            if not name or name in seen:
                continue
            cleaned.append(name)
            seen.add(name)
        portable["group_by"] = cleaned or ["instance_id"]

    @staticmethod
    def _ensure_query_condition(portable, plugin=None):
        query = portable.get("query_condition")
        if isinstance(query, dict) and query.get("type") in {"formula", "metric", "pmq"}:
            PolicyService._stamp_query_plugin(query, plugin)
            return
        metric_name = str(portable.get("metric_name") or "").strip()
        if not metric_name:
            return
        query = {
            "type": "metric",
            "metric_name": metric_name,
            "filter": list(portable.get("filter") or []),
        }
        PolicyService._stamp_query_plugin(query, plugin)
        portable["query_condition"] = query

    @staticmethod
    def _related_policy_count(template):
        count = getattr(template, "related_policy_count", None)
        if count is not None:
            return int(count)
        if not getattr(template, "pk", None):
            return 0
        return template.issued_policies.count()

    @staticmethod
    def _json_equal(left, right):
        return json.dumps(left, sort_keys=True, default=str) == json.dumps(right, sort_keys=True, default=str)

    @staticmethod
    def recipe_fields_from_template(template):
        config = PolicyService.portable_config(
            template.config or {},
            monitor_object=template.monitor_object,
            plugin=template.plugin,
        )
        group_algorithm, algorithm = normalize_template_algorithms(config)
        metric_unit = normalize_stored_metric_unit(
            config.get("metric_unit") or "",
            str(config.get("data_type") or ""),
        )
        default_calculation_unit = normalize_default_calculation_unit(metric_unit)
        forecast_target = config.get("forecast_target")
        if forecast_target in ("", None):
            forecast_target = None
        elif isinstance(forecast_target, (int, float)):
            forecast_target = float(forecast_target)
        return {
            "alert_name": config.get("alert_name") or template.name or "",
            "query_condition": PolicyService._runtime_query_condition(
                config.get("query_condition"),
                template.monitor_object,
                plugin=template.plugin,
            ),
            "threshold": copy.deepcopy(config.get("threshold") or []),
            "group_algorithm": group_algorithm,
            "algorithm": algorithm,
            "group_by": copy.deepcopy(config.get("group_by") or ["instance_id"]),
            "metric_unit": metric_unit,
            "calculation_unit": config.get("calculation_unit") or default_calculation_unit,
            "threshold_unit": (config.get("threshold_unit") or config.get("calculation_unit") or default_calculation_unit or ""),
            "compare_mode": config.get("compare_mode") or "absolute",
            "compare_value_kind": config.get("compare_value_kind") or "",
            "compare_offset_hours": config.get("compare_offset_hours"),
            "compare_offset_days": config.get("compare_offset_days"),
            "compare_baseline_weeks": config.get("compare_baseline_weeks"),
            "count_predicate": copy.deepcopy(config.get("count_predicate") or {}),
            "forecast_target": forecast_target,
            "forecast_target_unit": config.get("forecast_target_unit") or "",
            "forecast_lookback": copy.deepcopy(config.get("forecast_lookback") or {}),
            "recovery_threshold": copy.deepcopy(config.get("recovery_threshold") or {}),
        }

    @staticmethod
    def _mark_new_alerts_closed(alerts_to_close, operator, reason):
        if not alerts_to_close:
            return []
        now = timezone.now()
        locked_alerts = list(
            MonitorAlert.objects.select_for_update().filter(id__in=[alert.id for alert in alerts_to_close], status="new").order_by("id")
        )
        if not locked_alerts:
            return []
        operation_log = {
            "action": "closed",
            "reason": reason,
            "operator": operator,
            "time": now.isoformat(),
        }
        for alert in locked_alerts:
            alert.status = "closed"
            alert.end_event_time = now
            alert.operator = operator
            alert.operation_logs = (alert.operation_logs or []) + [operation_log]
            alert.alert_center_notified = False
        MonitorAlert.objects.bulk_update(
            locked_alerts,
            fields=["status", "end_event_time", "operator", "operation_logs", "alert_center_notified"],
        )
        record_lifecycle_events(
            locked_alerts,
            MonitorEvent.Action.CLOSED,
            event_time=now,
            operator=operator,
            reason=reason,
        )
        return locked_alerts

    @staticmethod
    def close_active_threshold_alerts_for_recipe_change(policy, old_query_condition, old_group_by, operator):
        reason = ""
        if not PolicyService._json_equal(old_group_by, policy.group_by):
            reason = "policy_group_by_changed"
        elif not PolicyService._json_equal(old_query_condition, policy.query_condition):
            reason = "policy_query_condition_changed"
        if not reason:
            return
        alerts_to_close = list(
            MonitorAlert.objects.filter(
                policy_id=policy.id,
                alert_type="alert",
                status="new",
            )
        )
        locked_alerts = PolicyService._mark_new_alerts_closed(alerts_to_close, operator, reason)
        if not locked_alerts:
            return
        notifier = AlertLifecycleNotifier(policy)
        notifier.enqueue_alert_center_deliveries(
            locked_alerts,
            "closed",
            operator=operator,
            reason=reason,
        )
        transaction.on_commit(
            lambda alerts=tuple(locked_alerts), current_policy=policy: AlertLifecycleNotifier(current_policy).notify_alerts(
                alerts,
                action="closed",
                operator=operator,
                reason=reason,
                notify_scope=NOTIFY_SCOPE_ALERT_CENTER_ONLY,
            )
        )

    @staticmethod
    def sync_issued_policies_from_template(template, user):
        recipe = PolicyService.recipe_fields_from_template(template)
        operator = getattr(user, "username", "") or "system"
        updated_count = 0
        last_id = 0
        while True:
            policies = list(
                MonitorPolicy.objects.filter(source_template_id=template.id, id__gt=last_id).order_by("id")[
                    : DatabaseConstants.BULK_UPDATE_BATCH_SIZE
                ]
            )
            if not policies:
                break
            last_id = policies[-1].id
            for policy in policies:
                changed_fields = []
                old_query_condition = copy.deepcopy(policy.query_condition)
                old_group_by = copy.deepcopy(policy.group_by)
                for field in POLICY_RECIPE_SYNC_FIELDS:
                    new_value = recipe[field]
                    old_value = getattr(policy, field)
                    if PolicyService._json_equal(old_value, new_value):
                        continue
                    setattr(policy, field, new_value)
                    changed_fields.append(field)
                if not changed_fields:
                    continue
                policy.updated_by = operator
                policy.save(update_fields=[*changed_fields, "updated_by", "updated_at"])
                PolicyService.close_active_threshold_alerts_for_recipe_change(
                    policy,
                    old_query_condition,
                    old_group_by,
                    operator,
                )
                updated_count += 1
        return updated_count

    @staticmethod
    def create_custom_template(*, organization, monitor_object_id, plugin_id, name, description, config, user):
        try:
            monitor_object = MonitorObject.objects.get(id=monitor_object_id)
            plugin = MonitorPlugin.objects.get(id=plugin_id, monitor_object=monitor_object)
        except (MonitorObject.DoesNotExist, MonitorPlugin.DoesNotExist) as exc:
            raise BaseAppException("监控对象或插件不存在") from exc
        return PolicyTemplate.objects.create(
            key=str(uuid.uuid4()),
            scope_key=f"custom:{organization}",
            template_type=PolicyTemplate.TYPE_CUSTOM,
            organization=organization,
            monitor_object=monitor_object,
            plugin=plugin,
            name=name,
            description=description or "",
            config=PolicyService.portable_config(config, monitor_object=monitor_object, plugin=plugin),
            created_by=user.username,
            updated_by=user.username,
            domain=getattr(user, "domain", "domain.com"),
            updated_by_domain=getattr(user, "domain", "domain.com"),
        )

    @staticmethod
    def update_custom_template(*, organization, template_key, name, description, config, user):
        templates = PolicyService.get_selected_templates([template_key], organization)
        template = templates[0]
        if template.template_type != PolicyTemplate.TYPE_CUSTOM:
            raise BaseAppException("内置模版不可编辑")
        if template.organization != organization:
            raise BaseAppException("无权限访问指定模板")
        template.name = name
        template.description = description or ""
        template.config = PolicyService.portable_config(
            config,
            monitor_object=template.monitor_object,
            plugin=template.plugin,
        )
        template.updated_by = user.username
        template.updated_by_domain = getattr(user, "domain", "domain.com")
        with transaction.atomic():
            template.save(update_fields=["name", "description", "config", "updated_by", "updated_by_domain", "updated_at"])
            updated_policy_count = PolicyService.sync_issued_policies_from_template(template, user)
        return template, updated_policy_count

    @staticmethod
    def parse_selection_keys(keys):
        if not isinstance(keys, list):
            raise BaseAppException("模板标识必须是列表")
        if len(keys) > MAX_ARCHIVE_TEMPLATES:
            raise BaseAppException(f"单次最多操作 {MAX_ARCHIVE_TEMPLATES} 个模板")
        ids = []
        for key in keys:
            try:
                _, raw_id = str(key).split(":", 1)
                ids.append(int(raw_id))
            except (TypeError, ValueError):
                raise BaseAppException(f"非法模板标识: {key}")
        if len(ids) != len(set(ids)):
            raise BaseAppException("模板标识不能重复")
        return ids

    @staticmethod
    def get_selected_templates(keys, organization):
        ids = PolicyService.parse_selection_keys(keys)
        templates = list(PolicyTemplate.objects.select_related("monitor_object", "plugin").filter(id__in=ids))
        if len(templates) != len(set(ids)):
            raise BaseAppException("模板不存在")
        templates_by_id = {item.id: item for item in templates}
        ordered_templates = []
        for key, template_id in zip(keys, ids):
            template = templates_by_id[template_id]
            template_type, _ = str(key).split(":", 1)
            if template_type != template.template_type:
                raise BaseAppException(f"模板标识不匹配: {key}")
            ordered_templates.append(template)
        for item in ordered_templates:
            if item.template_type == PolicyTemplate.TYPE_CUSTOM and item.organization != organization:
                raise BaseAppException("无权限访问指定模板")
        return ordered_templates

    @staticmethod
    def export_archive(keys, organization):
        selected_templates = PolicyService.get_selected_templates(keys, organization)
        templates_by_key = {}
        for template in selected_templates:
            current = templates_by_key.get(template.key)
            if current is None or template.template_type == PolicyTemplate.TYPE_CUSTOM:
                templates_by_key[template.key] = template
        buffer = io.BytesIO()
        manifest_items = []
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for template in templates_by_key.values():
                portable_identity = f"{template.template_type}:{template.key}"
                filename = f"templates/{hashlib.sha256(portable_identity.encode('utf-8')).hexdigest()}.json"
                payload = {
                    "key": template.key,
                    "name": template.name,
                    "description": template.description,
                    "monitor_object": template.monitor_object.name,
                    "plugin": template.plugin.name,
                    "config": template.config,
                }
                archive.writestr(filename, json.dumps(payload, ensure_ascii=False, indent=2))
                manifest_items.append({"file": filename, "key": template.key})
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format": ARCHIVE_FORMAT,
                        "schema_version": ARCHIVE_SCHEMA_VERSION,
                        "exported_at": timezone.now().isoformat(),
                        "templates": manifest_items,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        buffer.seek(0)
        return buffer

    @staticmethod
    def _read_archive(upload):
        content = upload.read(MAX_ARCHIVE_BYTES + 1)
        if len(content) > MAX_ARCHIVE_BYTES:
            raise BaseAppException("ZIP 包不能超过 10MB")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                names = [member.filename for member in members]
                if len(members) > MAX_ARCHIVE_FILES:
                    raise BaseAppException("ZIP 包文件数量超过限制")
                if len(names) != len(set(names)):
                    raise BaseAppException("ZIP 包包含重复文件名")
                total_size = 0
                for member in members:
                    path = PurePosixPath(member.filename)
                    if member.is_dir() or path.is_absolute() or ".." in path.parts or "\\" in member.filename:
                        raise BaseAppException("ZIP 包包含非法路径")
                    mode = member.external_attr >> 16
                    if mode & 0o170000 == 0o120000:
                        raise BaseAppException("ZIP 包不能包含符号链接")
                    if member.file_size > MAX_TEMPLATE_BYTES:
                        raise BaseAppException("ZIP 包单个文件不能超过 2MB")
                    total_size += member.file_size
                    if member.compress_size and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO:
                        raise BaseAppException("ZIP 包压缩比异常")
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    raise BaseAppException("ZIP 包解压后大小超过限制")
                try:
                    manifest = json.loads(archive.read("manifest.json"))
                except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise BaseAppException("ZIP 包缺少有效的 manifest.json") from exc
                if not isinstance(manifest, dict):
                    raise BaseAppException("manifest.json 必须是对象")
                if manifest.get("format") != ARCHIVE_FORMAT or manifest.get("schema_version") != ARCHIVE_SCHEMA_VERSION:
                    raise BaseAppException("不支持的模板 ZIP 格式或版本")
                template_items = manifest.get("templates")
                if not isinstance(template_items, list) or not template_items:
                    raise BaseAppException("manifest.json 缺少模板清单")
                if len(template_items) > MAX_ARCHIVE_TEMPLATES:
                    raise BaseAppException(f"单次最多导入 {MAX_ARCHIVE_TEMPLATES} 个模板")
                payloads = []
                for item in template_items:
                    if not isinstance(item, dict):
                        raise BaseAppException("manifest.json 包含非法模板项")
                    filename = item.get("file")
                    if not filename or filename not in names or not filename.startswith("templates/"):
                        raise BaseAppException("manifest 引用了非法的模板文件")
                    try:
                        payload = json.loads(archive.read(filename))
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        raise BaseAppException(f"模板文件无效: {filename}") from exc
                    if not isinstance(payload, dict) or item.get("key") != payload.get("key"):
                        raise BaseAppException(f"模板清单与文件不匹配: {filename}")
                    payloads.append(payload)
                return payloads
        except zipfile.BadZipFile as exc:
            raise BaseAppException("上传文件不是有效的 ZIP 包") from exc

    @staticmethod
    def import_archive(upload, *, organization, user, overwrite=False, authorize_monitor_object=None):
        payloads = PolicyService._read_archive(upload)
        prepared = []
        conflicts = []
        package_keys = set()
        for payload in payloads:
            key = str(payload.get("key") or "").strip()
            name = str(payload.get("name") or "").strip()
            if not key or not name or not isinstance(payload.get("config"), dict):
                raise BaseAppException("模板缺少 key、name 或 config")
            if len(key) > 255 or len(name) > 100:
                raise BaseAppException(f"模板标识或名称过长: {name}")
            try:
                monitor_object = MonitorObject.objects.get(name=payload.get("monitor_object"))
                plugin = MonitorPlugin.objects.get(name=payload.get("plugin"), monitor_object=monitor_object)
            except (MonitorObject.DoesNotExist, MonitorPlugin.DoesNotExist) as exc:
                raise BaseAppException(f"模板 {name} 引用的监控对象或插件不存在") from exc
            if authorize_monitor_object:
                authorize_monitor_object(monitor_object.id)
            if key in package_keys:
                raise BaseAppException(f"ZIP 包内模板重复: {name}")
            package_keys.add(key)
            config = PolicyService.portable_config(
                payload["config"],
                monitor_object=monitor_object,
                plugin=plugin,
            )
            PolicyService._runtime_query_condition(config.get("query_condition"), monitor_object, plugin=plugin)
            payload["config"] = config
            existing = PolicyTemplate.objects.filter(
                template_type=PolicyTemplate.TYPE_CUSTOM,
                organization=organization,
                key=key,
            ).first()
            if existing:
                conflicts.append({"id": existing.id, "name": existing.name})
            prepared.append((payload, monitor_object, plugin, existing))
        if conflicts and not overwrite:
            return {"requires_overwrite": True, "conflicts": conflicts, "imported_count": 0, "updated_policy_count": 0}

        updated_policy_count = 0
        with transaction.atomic():
            for payload, monitor_object, plugin, existing in prepared:
                values = {
                    "key": payload["key"],
                    "scope_key": f"custom:{organization}",
                    "template_type": PolicyTemplate.TYPE_CUSTOM,
                    "organization": organization,
                    "monitor_object": monitor_object,
                    "plugin": plugin,
                    "name": payload["name"],
                    "description": payload.get("description") or "",
                    "config": payload["config"],
                    "updated_by": user.username,
                    "updated_by_domain": getattr(user, "domain", "domain.com"),
                }
                if existing:
                    for field, value in values.items():
                        setattr(existing, field, value)
                    existing.save()
                    updated_policy_count += PolicyService.sync_issued_policies_from_template(existing, user)
                else:
                    PolicyTemplate.objects.create(
                        **values,
                        created_by=user.username,
                        domain=getattr(user, "domain", "domain.com"),
                    )
        return {
            "requires_overwrite": False,
            "conflicts": conflicts,
            "imported_count": len(prepared),
            "updated_policy_count": updated_policy_count,
        }
