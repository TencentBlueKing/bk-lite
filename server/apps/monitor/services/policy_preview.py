import re
import time
from copy import deepcopy

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.expression.conditions import compile_filter_to_query
from apps.monitor.expression.errors import FormulaError
from apps.monitor.expression.query import build_formula_query
from apps.monitor.expression.validators import (
    validate_formula_condition,
    validate_multi_condition,
)
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.services.chart_unit import (
    convert_vm_result_copy,
    resolve_chart_unit,
)
from apps.monitor.tasks.utils.policy_methods import (
    compile_policy_query,
    period_to_seconds,
    resolve_result_unit,
)
from apps.monitor.tasks.utils.policy_multi import compile_condition_query, condition_policy_like
from apps.monitor.utils.unit_converter import UnitConverter
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class PolicyPreviewService:
    def __init__(self, payload):
        self.payload = payload or {}
        self.warnings = []
        self.metric = None

    def preview(self):
        query_condition = self._require_dict("query_condition")
        if query_condition.get("type") == "multi":
            return self._preview_multi(query_condition)
        period = self._require_dict("period")
        self._require_value("algorithm")
        step = self._format_period(period)
        if query_condition.get("type") == "formula":
            compiled_formula = build_formula_query(
                query_condition,
                base_filters_by_ref=self._build_formula_instance_filters(query_condition),
            )
            metric_query = compiled_formula.query
            group_by = compiled_formula.group_by
            self.warnings.extend(compiled_formula.warnings)
        else:
            group_by = self._require_string_list("group_by")
            metric_query = self._build_metric_query(query_condition)

        group_by_clause = ",".join(group_by)
        query = compile_policy_query(self.payload, metric_query, step, group_by_clause)
        end = int(time.time())
        points = self._preview_points()
        start = end - period_to_seconds(period) * points
        result_unit = resolve_result_unit(self.payload)
        data = VictoriaMetricsAPI().query_range(query, start, end, step)
        self._raise_for_vm_error(data)
        chart_unit = self._comparison_chart_unit(result_unit)
        source_unit = (
            chart_unit
            if not result_unit.conversion_enabled
            else self._chart_source_unit(query_condition.get("type"))
        )
        data, chart_unit = self._convert_preview_chart(
            data, source_unit, chart_unit
        )

        data["unit"] = (
            UnitConverter.get_display_unit(chart_unit) if chart_unit else ""
        )

        return {
            "query": query,
            "data": data,
            "chart_unit": chart_unit,
            "result_unit": result_unit.unit,
            "overlay": False,
            "threshold": self._preview_thresholds(),
            "warnings": self.warnings,
        }

    def _preview_multi(self, query_condition):
        period = self._require_dict("period")
        step = self._format_period(period)
        try:
            validated = validate_multi_condition(query_condition)
        except FormulaError as exc:
            raise BaseAppException(str(exc)) from exc
        self.warnings.extend(validated.warnings)
        queries = query_condition.get("queries") or []
        filters_by_ref, metrics = self._instance_filters_for_queries(
            [item for item in queries if item.get("source") != "formula"]
        )
        end = int(time.time())
        points = self._preview_points()
        start = end - period_to_seconds(period) * points
        api = VictoriaMetricsAPI()
        cards = []
        for condition in queries:
            if condition.get("source") == "formula":
                cards.append(self._preview_formula_condition(condition, step, api, start, end))
                continue
            metric = metrics[condition["metric_id"]]
            base_query = compile_filter_to_query(
                metric.query or "",
                deepcopy(condition.get("filter") or []),
                base_filters=filters_by_ref.get(condition.get("ref")) or None,
            )
            query = compile_condition_query(self.payload, condition, base_query, step)
            data = api.query_range(query, start, end, step)
            self._raise_for_vm_error(data)
            cards.append(self._preview_condition_card(condition, metric, query, data))
        first = cards[0]
        return {
            "query": first["query"],
            "data": first["data"],
            "chart_unit": first["chart_unit"],
            "result_unit": first["result_unit"],
            "overlay": False,
            "threshold": first["threshold"],
            "warnings": self.warnings,
            "conditions": cards,
        }

    def _instance_filters_for_queries(self, queries):
        preview = self._require_dict("preview")
        values = preview.get("instance_id_values")
        if not values:
            raise BaseAppException("preview.instance_id_values is required")
        metric_ids = [item["metric_id"] for item in queries]
        metrics = {metric.id: metric for metric in Metric.objects.filter(id__in=metric_ids)}
        filters_by_ref = {}
        for item in queries:
            metric = metrics.get(item["metric_id"])
            if not metric:
                raise BaseAppException(f"metric does not exist [{item['metric_id']}]")
            filters = []
            for key, value in zip(getattr(metric, "instance_id_keys", []) or [], values):
                filters.append(
                    {
                        "name": key,
                        "method": "=~",
                        "value": self._escape_regex_value(value),
                    }
                )
            filters_by_ref[item.get("ref")] = filters
        return filters_by_ref, metrics

    def _preview_formula_condition(self, condition, step, api, start, end):
        formula = {
            "type": "formula",
            "result_name": condition.get("metric_name") or condition.get("ref") or "",
            "expression": condition.get("expression") or "",
            "queries": condition.get("operands") or [],
        }
        compiled = build_formula_query(
            formula,
            base_filters_by_ref=self._build_formula_instance_filters(formula),
        )
        query = compile_condition_query(self.payload, condition, compiled.query, step)
        data = api.query_range(query, start, end, step)
        self._raise_for_vm_error(data)
        return self._preview_condition_card(
            condition,
            None,
            query,
            data,
            metric_name=str(condition.get("metric_name") or condition.get("ref") or ""),
        )

    def _preview_condition_card(self, condition, metric, query, data, metric_name=None):
        result_unit = resolve_result_unit(condition_policy_like(self.payload, condition))
        if not result_unit.conversion_enabled:
            chart_unit = result_unit.unit or ""
            source_unit = chart_unit
        else:
            chart_unit = condition.get("calculation_unit") or result_unit.unit or ""
            source_unit = condition.get("metric_unit") or (getattr(metric, "unit", "") if metric else "") or chart_unit
        data, chart_unit = self._convert_preview_chart(data, source_unit, chart_unit)
        data["unit"] = UnitConverter.get_display_unit(chart_unit) if chart_unit else ""
        if not metric_name:
            metric_name = condition.get("ref")
            if metric is not None:
                metric_name = metric.display_name or metric.name or metric_name
        return {
            "ref": condition.get("ref"),
            "role": condition.get("role"),
            "metric_name": metric_name,
            "query": query,
            "data": data,
            "chart_unit": chart_unit,
            "result_unit": result_unit.unit,
            "threshold": deepcopy(condition.get("threshold") or []),
        }

    def _comparison_chart_unit(self, result_unit):
        if not result_unit.conversion_enabled:
            return result_unit.unit or ""
        return self._chart_unit()

    def _convert_preview_chart(self, data, source_unit, chart_unit):
        source = source_unit or chart_unit or ""
        target = chart_unit or source
        if (
            source
            and target
            and source != target
            and not UnitConverter.is_convertible(source, target)
        ):
            target = source
        return convert_vm_result_copy(data, source, target), target

    @staticmethod
    def _raise_for_vm_error(data):
        if data.get("status") in (None, "success"):
            return
        message = data.get("error") or data.get("message") or data.get("errorType") or "VictoriaMetrics query failed"
        raise BaseAppException(message)

    def _build_metric_query(self, query_condition):
        if query_condition.get("type") == "pmq":
            query = query_condition.get("query")
            if not query:
                raise BaseAppException("query_condition.query is required")
            return query

        metric_id = query_condition.get("metric_id")
        if not metric_id:
            raise BaseAppException("query_condition.metric_id is required")

        self.metric = Metric.objects.filter(id=metric_id).first()
        if not self.metric:
            raise BaseAppException(f"metric does not exist [{metric_id}]")

        return compile_filter_to_query(
            self.metric.query or "",
            deepcopy(query_condition.get("filter") or []),
            base_filters=self._build_instance_filters(),
        )

    def _build_instance_filters(self):
        preview = self._require_dict("preview")
        values = preview.get("instance_id_values")
        if not values:
            raise BaseAppException("preview.instance_id_values is required")

        keys = getattr(self.metric, "instance_id_keys", []) or []
        if not keys:
            return []

        filters = []
        for key, value in zip(keys, values):
            filters.append(
                {
                    "name": key,
                    "method": "=~",
                    "value": self._escape_regex_value(value),
                }
            )
        return filters

    def _build_formula_instance_filters(self, query_condition):
        try:
            validate_formula_condition(query_condition)
        except FormulaError as exc:
            raise BaseAppException(str(exc)) from exc

        preview = self._require_dict("preview")
        values = preview.get("instance_id_values")
        if not values:
            raise BaseAppException("preview.instance_id_values is required")

        metric_ids = [item["metric_id"] for item in query_condition.get("queries") or []]
        metrics = Metric.objects.filter(id__in=metric_ids)
        metrics_by_id = {metric.id: metric for metric in metrics}

        filters_by_ref = {}
        for item in query_condition.get("queries") or []:
            metric = metrics_by_id.get(item["metric_id"])
            if not metric:
                raise BaseAppException(f"metric does not exist [{item['metric_id']}]")
            filters = []
            for key, value in zip(getattr(metric, "instance_id_keys", []) or [], values):
                filters.append(
                    {
                        "name": key,
                        "method": "=~",
                        "value": self._escape_regex_value(value),
                    }
                )
            filters_by_ref[item["ref"]] = filters
        return filters_by_ref

    @staticmethod
    def _escape_regex_value(value):
        return re.sub(r'([\\^$.*+?()[\]{}|"])', r"\\\1", str(value if value is not None else ""))

    def _chart_unit(self):
        return resolve_chart_unit(
            self.payload.get("metric_unit")
            or getattr(self.metric, "unit", "")
            or "",
            self.payload.get("calculation_unit") or "",
            self.payload.get("threshold_unit") or "",
        )

    def _chart_source_unit(self, query_type):
        if query_type == "formula":
            return self.payload.get("calculation_unit") or ""
        return (
            self.payload.get("metric_unit")
            or getattr(self.metric, "unit", "")
            or ""
        )

    def _preview_thresholds(self):
        return deepcopy(self.payload.get("threshold") or [])

    def _preview_points(self):
        preview = self.payload.get("preview") or {}
        try:
            points = int(preview.get("duration_points") or 30)
        except (TypeError, ValueError):
            points = 30
        return max(1, points)

    def _format_period(self, period):
        period_type = period.get("type")
        value = period.get("value")
        if not value:
            raise BaseAppException("period.value is required")
        unit_map = {
            "min": "m",
            "hour": "h",
            "day": "d",
        }
        if period_type not in unit_map:
            raise BaseAppException(f"invalid period type: {period_type}")
        return f"{value}{unit_map[period_type]}"

    def _require_dict(self, key):
        value = self.payload.get(key)
        if not isinstance(value, dict):
            raise BaseAppException(f"{key} is required")
        return value

    def _require_list(self, key):
        value = self.payload.get(key)
        if not isinstance(value, list) or not value:
            raise BaseAppException(f"{key} is required")
        return value

    def _require_string_list(self, key):
        value = self._require_list(key)
        result = []
        seen = set()
        for item in value:
            item = str(item or "").strip()
            if item and item not in seen:
                result.append(item)
                seen.add(item)
        if not result:
            raise BaseAppException(f"{key} is required")
        return result

    def _require_value(self, key):
        value = self.payload.get(key)
        if not value:
            raise BaseAppException(f"{key} is required")
        return value
