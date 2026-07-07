import re
import time
from copy import deepcopy

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.expression.conditions import compile_filter_to_query
from apps.monitor.expression.query import build_formula_query
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.tasks.utils.policy_methods import (
    METHOD,
    build_formula_policy_query,
    build_policy_query,
    period_to_seconds,
    query_formula_policy_metrics,
)
from apps.monitor.utils.unit_converter import UnitConverter


class PolicyPreviewService:
    def __init__(self, payload):
        self.payload = payload or {}
        self.warnings = []
        self.metric = None

    def preview(self):
        query_condition = self._require_dict("query_condition")
        period = self._require_dict("period")
        algorithm = self._require_value("algorithm")
        group_algorithm = self.payload.get("group_algorithm")
        step = self._format_period(period)
        if query_condition.get("type") == "formula":
            compiled_formula = build_formula_query(query_condition)
            metric_query = compiled_formula.query
            group_by = compiled_formula.group_by
            self.warnings.extend(compiled_formula.warnings)
            query = build_formula_policy_query(algorithm, metric_query, step)
        else:
            group_by = self._require_string_list("group_by")
            metric_query = self._build_metric_query(query_condition)
            query = build_policy_query(algorithm, metric_query, step, ",".join(group_by), group_algorithm)

        group_by_clause = ",".join(group_by)
        method = METHOD.get(algorithm)
        if not method:
            raise BaseAppException(f"invalid algorithm method: {algorithm}")

        end = int(time.time())
        points = self._preview_points()
        start = end - period_to_seconds(period) * points
        if query_condition.get("type") == "formula":
            data = query_formula_policy_metrics(algorithm, metric_query, start, end, step)
        else:
            data = method(metric_query, start, end, step, group_by_clause, group_algorithm)
        self._raise_for_vm_error(data)
        data = self._apply_unit_conversion(data)
        data["unit"] = self._display_unit()

        return {
            "query": query,
            "data": data,
            "warnings": self.warnings,
        }

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

    @staticmethod
    def _escape_regex_value(value):
        return re.sub(r'([\\^$.*+?()[\]{}|"])', r"\\\1", str(value if value is not None else ""))

    def _apply_unit_conversion(self, data):
        source_unit = self.payload.get("metric_unit") or getattr(self.metric, "unit", "") or ""
        target_unit = self.payload.get("calculation_unit") or ""
        if not source_unit or not target_unit or source_unit == target_unit:
            return data
        if not UnitConverter.is_convertible(source_unit, target_unit):
            self.warnings.append(f"unit conversion skipped: {source_unit} -> {target_unit}")
            return data

        for result in data.get("data", {}).get("result", []):
            values = result.get("values") or []
            converted = UnitConverter.convert_values([float(item[1]) for item in values], source_unit, target_unit)
            for index, (timestamp, _) in enumerate(values):
                values[index] = [timestamp, str(converted[index])]
        return data

    def _display_unit(self):
        target_unit = self.payload.get("calculation_unit") or ""
        source_unit = self.payload.get("metric_unit") or getattr(self.metric, "unit", "") or ""
        return UnitConverter.get_display_unit(target_unit or source_unit) if (target_unit or source_unit) else ""

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
