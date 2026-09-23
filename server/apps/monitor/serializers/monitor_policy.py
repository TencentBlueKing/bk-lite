import math
import re

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.tasks.utils.policy_methods import (
    ALLOWED_FORECAST_LOOKBACK,
    COMPARE_MODE_BASELINE_DAYS,
    COMPARE_SPAN_CONFLICT_MESSAGE,
    span_value_message,
    COMPARE_MODE_BASELINE_WEEKS,
    COMPARE_MODE_OFFSET_DAYS,
    COMPARE_MODE_OFFSET_HOURS,
    COMPARE_MODES,
    MAX_COMPARE_BASELINE_WEEKS,
    MAX_COMPARE_OFFSET_DAYS,
    MAX_COMPARE_OFFSET_HOURS,
    COMPARE_OFFSET_SECONDS,
    COMPARE_VALUE_KINDS,
    COMPARE_VALUE_KINDS_BY_MODE,
    COUNT_IF_ALGORITHM,
    GROUP_AGGREGATION_ALGORITHMS,
    HIGH_SIDE_METHODS,
    LEVEL_ALGORITHMS,
    LOW_SIDE_METHODS,
    NEW_ALGORITHMS,
    PER_SERIES_ALGORITHMS,
    POLICY_ALGORITHMS,
    PREDICATE_TO_PROMQL,
    base_query_contains_rate_function,
    period_to_seconds,
    resolve_result_unit,
)
from apps.monitor.utils.unit_converter import UnitConverter
from rest_framework import serializers

# 阈值条件合法等级 —— 取自 MonitorPolicy.LEVEL_CHOICES 的用户可选档（排除系统在无数据时自动生成的 no_data）
_VALID_THRESHOLD_LEVELS = {"info", "warning", "error", "critical"}
# source 合法类型 —— 其余类型在扫描器/基线构建时静默返回空目标（策略不生效），instance/organization 之外即误配
_VALID_SOURCE_TYPES = {"instance", "organization"}
_VALID_GROUP_AGGREGATION_ALGORITHMS = GROUP_AGGREGATION_ALGORITHMS
_VALID_AGGREGATION_ALGORITHMS = POLICY_ALGORITHMS
# PromQL/MetricsQL label 运算符白名单
_VALID_LABEL_METHODS = {"=", "!=", "=~", "!~"}
# label name 合法正则（Prometheus 规范）
_LABEL_NAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


class MonitorPolicySerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        data_team_ids = self.context.get("data_team_ids")
        # 列表/告警嵌套投影可按当前数据范围裁剪可见组织；详情与编辑必须返回完整归属，
        # 否则跨组织编辑会把兄弟组织从表单中抹掉，保存时造成配置丢失。
        if self.context.get("filter_organizations") and data_team_ids is not None:
            representation["organizations"] = [
                organization for organization in representation.get("organizations", []) if organization in data_team_ids
            ]
        return representation

    def _validate_policy_handlers(self, attrs):
        handlers_provided = "handlers" in attrs
        organizations_provided = "organizations" in attrs
        if not handlers_provided and not organizations_provided:
            return attrs
        from apps.monitor.services.alert_handlers import AlertHandlerInvalid, normalize_policy_handlers

        handlers = attrs["handlers"] if handlers_provided else list(getattr(self.instance, "handlers", None) or [])
        organizations = (
            attrs["organizations"] if organizations_provided else list(getattr(self.instance, "organizations", None) or [])
        )
        try:
            resolved = normalize_policy_handlers(handlers, organizations)
        except AlertHandlerInvalid as exc:
            raise serializers.ValidationError({"handlers": str(exc)}) from exc
        if handlers_provided:
            attrs["handlers"] = resolved
        return attrs

    class Meta:
        model = MonitorPolicy
        fields = "__all__"

    def validate_threshold(self, value):
        """校验阈值列表：每条须含合法 method/value/level，否则后台扫描计算阈值时崩。

        仅校验已填写的阈值条目（空列表=未配阈值，放行）。只挡下游 policy_calculate 一定会
        KeyError/BaseAppException 的非法配置（缺 method/value/level、method 不在合法运算符内），
        把错误从「后台扫描时静默报错」前移到 API 边界，不误伤当前可用配置。
        """
        if not value:
            return value
        if not isinstance(value, list):
            raise serializers.ValidationError("threshold 必须是列表")
        valid_methods = set(AlertConstants.THRESHOLD_METHODS)
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f"threshold[{index}] 必须是对象")
            if item.get("method") not in valid_methods:
                raise serializers.ValidationError(f"threshold[{index}].method 非法，须为 {sorted(valid_methods)} 之一")
            if "value" not in item:
                raise serializers.ValidationError(f"threshold[{index}] 缺少 value")
            raw_value = item.get("value")
            if isinstance(raw_value, bool):
                raise serializers.ValidationError(
                    f"threshold[{index}].value 必须是有限数值"
                )
            try:
                number = float(raw_value)
            except (TypeError, ValueError) as err:
                raise serializers.ValidationError(
                    f"threshold[{index}].value 必须是有限数值"
                ) from err
            if not math.isfinite(number):
                raise serializers.ValidationError(
                    f"threshold[{index}].value 必须是有限数值"
                )
            if item.get("level") not in _VALID_THRESHOLD_LEVELS:
                raise serializers.ValidationError(f"threshold[{index}].level 非法，须为 {sorted(_VALID_THRESHOLD_LEVELS)} 之一")
        return value

    def _get_value(self, attrs, field, default):
        if field in attrs:
            return attrs[field]
        if self.instance is not None:
            return getattr(self.instance, field, default)
        return default

    def get_effective_units(self, attrs):
        metric_unit = self._get_value(attrs, "metric_unit", "") or ""
        calculation_unit = (
            self._get_value(attrs, "calculation_unit", "") or metric_unit
        )
        threshold_unit = (
            self._get_value(attrs, "threshold_unit", "") or calculation_unit
        )
        return calculation_unit, threshold_unit

    def validate(self, attrs):
        attrs = super().validate(attrs)
        attrs = self._validate_policy_handlers(attrs)
        attrs = self._validate_calc_enrichment(attrs)
        relevant_fields = {
            "threshold",
            "metric_unit",
            "calculation_unit",
            "threshold_unit",
            "query_condition",
            "algorithm",
            "compare_mode",
            "compare_value_kind",
        }
        if self.instance is not None and not relevant_fields.intersection(attrs):
            return attrs

        threshold = self._get_value(attrs, "threshold", [])
        if not threshold:
            return attrs

        query_condition = self._get_value(attrs, "query_condition", {}) or {}
        result_unit = resolve_result_unit(self._result_unit_policy_like(attrs))
        calculation_unit, threshold_unit = self.get_effective_units(attrs)
        if not result_unit.conversion_enabled:
            if result_unit.unit in {"hour", "count", ""}:
                return attrs
            if result_unit.unit and not UnitConverter.is_known_unit(result_unit.unit):
                raise serializers.ValidationError({"calculation_unit": "结果单位无效"})
            effective_threshold = threshold_unit or result_unit.unit
            if (
                result_unit.unit
                and effective_threshold
                and effective_threshold != result_unit.unit
            ):
                raise serializers.ValidationError(
                    {
                        "threshold_unit": (
                            f"阈值单位必须与结果单位 {result_unit.unit} 一致"
                        )
                    }
                )
            return attrs

        if not calculation_unit and not threshold_unit:
            # Trap、枚举指标与历史 PMQ 策略没有数值单位，保持现有契约。
            if query_condition.get("type") in {"pmq", "metric"}:
                return attrs
            raise serializers.ValidationError(
                {"threshold_unit": "数值型告警阈值必须配置结果单位和阈值单位"}
            )

        if not UnitConverter.is_known_unit(calculation_unit):
            raise serializers.ValidationError(
                {"calculation_unit": "结果单位无效"}
            )
        if not UnitConverter.is_known_unit(threshold_unit):
            raise serializers.ValidationError({"threshold_unit": "阈值单位无效"})
        if not UnitConverter.is_convertible(threshold_unit, calculation_unit):
            raise serializers.ValidationError(
                {
                    "threshold_unit": (
                        f"阈值单位 {threshold_unit} 不能转换为结果单位 "
                        f"{calculation_unit}"
                    )
                }
            )
        return attrs

    def validate_trigger_count(self, value):
        """校验阈值告警触发条件：连续 N 个汇聚周期满足阈值，N 必须为正整数。"""
        if not isinstance(value, int) or isinstance(value, bool):
            raise serializers.ValidationError("trigger_count 必须是正整数")
        if value < 1:
            raise serializers.ValidationError("trigger_count 必须大于等于 1")
        return value

    def validate_query_condition(self, value):
        """校验查询条件结构完整性，并对 filter 条件执行注入防护。

        结构校验：pmq 自定义查询须带非空 query，否则（指标型）须带 metric_id。
        注入防护：对 filter 列表中每个条件的 label name 和运算符执行白名单校验，
                  防止 PromQL/MetricsQL 注入落库。
        """
        if not value:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("query_condition 必须是对象")

        query_type = value.get("type")
        if query_type == "pmq":
            if not value.get("query"):
                raise serializers.ValidationError("query_condition.type=pmq 时必须提供非空 query")
            # pmq 类型直接传原始 PromQL，不校验 filter
            return value

        if query_type == "formula":
            from apps.core.exceptions.base_app_exception import BaseAppException
            from apps.monitor.expression.query import build_formula_query

            try:
                build_formula_query(value)
            except BaseAppException as err:
                raise serializers.ValidationError(str(err)) from err
            return value

        if "metric_id" not in value:
            raise serializers.ValidationError("query_condition 缺少 metric_id")

        # 校验 filter 中的 label name 和运算符，防止注入
        filter_list = value.get("filter", [])
        if not isinstance(filter_list, list):
            raise serializers.ValidationError("query_condition.filter 必须是数组")

        for idx, condition in enumerate(filter_list):
            if not isinstance(condition, dict):
                continue
            name = condition.get("name", "")
            method = condition.get("method", "")
            if name and not _LABEL_NAME_RE.match(str(name)):
                raise serializers.ValidationError(
                    f"filter[{idx}].name={name!r} 包含非法字符，只允许 [a-zA-Z_][a-zA-Z0-9_]*"
                )
            if method and method not in _VALID_LABEL_METHODS:
                raise serializers.ValidationError(
                    f"filter[{idx}].method={method!r} 不是合法运算符，只允许 {sorted(_VALID_LABEL_METHODS)}"
                )
            if isinstance(condition.get("value"), (list, tuple, set, dict)):
                raise serializers.ValidationError(f"filter[{idx}].value 必须是标量")
        return value

    def validate_source(self, value):
        """校验策略适用资源：非空时须含 type 与 values，且 type 为 instance/organization。

        空 dict 放行；缺 type/values 会让扫描器/基线构建 KeyError，未知 type 则静默无目标=策略不生效。
        """
        if not value:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("source 必须是对象")
        if "type" not in value or "values" not in value:
            raise serializers.ValidationError("source 必须同时包含 type 与 values")
        if value.get("type") not in _VALID_SOURCE_TYPES:
            raise serializers.ValidationError(f"source.type 非法，须为 {sorted(_VALID_SOURCE_TYPES)} 之一")
        return value

    def validate_algorithm(self, value):
        """校验周期聚合算法须为下游支持的 over_time 函数。"""
        if value and value not in _VALID_AGGREGATION_ALGORITHMS:
            raise serializers.ValidationError(f"algorithm 非法，须为 {sorted(_VALID_AGGREGATION_ALGORITHMS)} 之一")
        return value

    def validate_group_algorithm(self, value):
        """校验分组聚合算法须为下游支持的聚合函数。"""
        if value and value not in _VALID_GROUP_AGGREGATION_ALGORITHMS:
            raise serializers.ValidationError(
                f"group_algorithm 非法，须为 {sorted(_VALID_GROUP_AGGREGATION_ALGORITHMS)} 之一"
            )
        return value

    def validate_group_by(self, value):
        """校验 group_by 首位必须是监控对象的实例主键，防止下游扫描链路误判实例归属。"""
        if not value:
            return value
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise serializers.ValidationError("group_by 必须是非空字符串列表")
        invalid_items = [item for item in value if not _LABEL_NAME_RE.match(item)]
        if invalid_items:
            raise serializers.ValidationError(f"group_by 包含非法字符：{', '.join(invalid_items)}")

        monitor_object = self._get_monitor_object()
        if monitor_object is None:
            return value

        instance_id_keys = getattr(monitor_object, "instance_id_keys", None)
        if not instance_id_keys:
            return value

        primary_key = instance_id_keys[0]
        if value[0] != primary_key:
            logger.warning(
                "group_by[0]=%s does not match instance_id_keys[0]=%s, auto-correcting",
                value[0],
                primary_key,
            )
            value = [primary_key] + [k for k in value if k != primary_key]

        # 多键对象（如 Docker Container、Process）若缺少子身份维度，扫描侧无法唯一归属实例。
        for key in instance_id_keys[1:]:
            if key not in value:
                logger.warning(
                    "group_by missing identity key %s for monitor object %s, auto-appending",
                    key,
                    getattr(monitor_object, "name", monitor_object),
                )
                value.append(key)

        return value

    def validate_compare_mode(self, value):
        if not value:
            return "absolute"
        if value not in COMPARE_MODES:
            raise serializers.ValidationError(
                f"compare_mode 非法，须为 {sorted(COMPARE_MODES)} 之一"
            )
        return value

    def validate_compare_value_kind(self, value):
        if not value:
            return ""
        if value not in COMPARE_VALUE_KINDS:
            raise serializers.ValidationError(
                f"compare_value_kind 非法，须为 {sorted(COMPARE_VALUE_KINDS)} 之一"
            )
        return value

    def validate_recovery_threshold(self, value):
        if not value:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("recovery_threshold 必须是对象")
        valid_methods = set(AlertConstants.THRESHOLD_METHODS)
        if value.get("method") not in valid_methods:
            raise serializers.ValidationError(
                f"recovery_threshold.method 非法，须为 {sorted(valid_methods)} 之一"
            )
        if "value" not in value:
            raise serializers.ValidationError("recovery_threshold 缺少 value")
        raw_value = value.get("value")
        if isinstance(raw_value, bool):
            raise serializers.ValidationError("recovery_threshold.value 必须是有限数值")
        try:
            number = float(raw_value)
        except (TypeError, ValueError) as err:
            raise serializers.ValidationError(
                "recovery_threshold.value 必须是有限数值"
            ) from err
        if not math.isfinite(number):
            raise serializers.ValidationError("recovery_threshold.value 必须是有限数值")
        return value

    def _result_unit_policy_like(self, attrs):
        return {
            "algorithm": self._get_value(attrs, "algorithm", ""),
            "compare_mode": self._get_value(attrs, "compare_mode", "absolute")
            or "absolute",
            "compare_value_kind": self._get_value(attrs, "compare_value_kind", "") or "",
            "metric_unit": self._get_value(attrs, "metric_unit", "") or "",
            "calculation_unit": self._get_value(attrs, "calculation_unit", "") or "",
        }

    def _compiled_base_query(self, attrs):
        query_condition = self._get_value(attrs, "query_condition", {}) or {}
        query_type = query_condition.get("type")
        if query_type == "pmq":
            return query_condition.get("query") or ""
        if query_type == "formula":
            from apps.core.exceptions.base_app_exception import BaseAppException
            from apps.monitor.expression.query import build_formula_query

            try:
                return build_formula_query(query_condition).query
            except BaseAppException:
                return ""
        metric_id = query_condition.get("metric_id")
        if not metric_id:
            return ""
        from apps.monitor.expression.conditions import compile_filter_to_query
        from apps.monitor.models.monitor_metrics import Metric

        metric = Metric.objects.filter(id=metric_id).first()
        if not metric:
            return ""
        return compile_filter_to_query(metric.query or "", query_condition.get("filter") or [])

    def _is_enum_metric(self, attrs):
        query_condition = self._get_value(attrs, "query_condition", {}) or {}
        if query_condition.get("type") != "metric":
            return False
        from apps.monitor.models.monitor_metrics import Metric

        metric = Metric.objects.filter(id=query_condition.get("metric_id")).first()
        return metric is not None and metric.data_type == "Enum"

    def _clear_trap_enrichment(self, attrs):
        attrs["compare_mode"] = "absolute"
        attrs["compare_value_kind"] = ""
        attrs["count_predicate"] = {}
        attrs["forecast_target"] = None
        attrs["forecast_target_unit"] = ""
        attrs["forecast_lookback"] = {}
        attrs["recovery_threshold"] = {}
        return attrs

    def _validate_calc_enrichment(self, attrs):
        collect_type = self._get_value(attrs, "collect_type", "") or ""
        if collect_type == "trap":
            return self._clear_trap_enrichment(attrs)

        algorithm = self._get_value(attrs, "algorithm", "") or ""
        compare_mode = self._get_value(attrs, "compare_mode", "absolute") or "absolute"
        compare_kind = self._get_value(attrs, "compare_value_kind", "") or ""
        query_condition = self._get_value(attrs, "query_condition", {}) or {}
        errors = {}

        allowed_kinds = COMPARE_VALUE_KINDS_BY_MODE.get(compare_mode)
        if allowed_kinds is not None and compare_kind not in allowed_kinds:
            errors["compare_value_kind"] = (
                f"compare_mode={compare_mode} 只允许 compare_value_kind 为 "
                f"{sorted(allowed_kinds)}"
            )

        if compare_mode == "timeleft" and algorithm not in LEVEL_ALGORITHMS:
            errors["algorithm"] = "距容量线剩余时间只允许 avg/max/min/last 类汇聚"
        if compare_mode == "timeleft" and not self._get_value(attrs, "forecast_target", None):
            errors.setdefault("forecast_target", "timeleft 必须填写容量线目标")
        if compare_mode == "timeleft":
            lookback = self._get_value(attrs, "forecast_lookback", None)
            if lookback in (None, {}):
                attrs["forecast_lookback"] = {"type": "hour", "value": 1}
            elif not isinstance(lookback, dict):
                errors["forecast_lookback"] = "回看窗格式非法"
            else:
                try:
                    lookback_key = (lookback.get("type"), int(lookback.get("value")))
                except (TypeError, ValueError):
                    lookback_key = None
                if lookback_key not in ALLOWED_FORECAST_LOOKBACK:
                    errors["forecast_lookback"] = "回看窗只允许 1h / 4h / 24h"
            thresholds = self._get_value(attrs, "threshold", []) or []
            trigger_methods = {
                item.get("method")
                for item in thresholds
                if isinstance(item, dict) and item.get("method")
            }
            if trigger_methods - LOW_SIDE_METHODS:
                errors["threshold"] = "距容量线剩余时间只允许 < / <= 阈值"
            unit = str(self._get_value(attrs, "forecast_target_unit", "") or "").strip()
            metric_unit = str(self._get_value(attrs, "metric_unit", "") or "").strip()
            if unit and (
                not metric_unit or not UnitConverter.is_convertible(unit, metric_unit)
            ):
                errors["forecast_target_unit"] = "容量线单位必须与指标单位属于同一量纲"
            attrs["forecast_target_unit"] = unit
        else:
            attrs["forecast_target_unit"] = ""

        if algorithm == COUNT_IF_ALGORITHM and compare_mode != "absolute":
            errors["compare_mode"] = "条件计数只允许比较基准为当前值"
        if algorithm in PER_SERIES_ALGORITHMS and query_condition.get("type") == "formula":
            errors["algorithm"] = "公式策略不能使用速率/变化次数/斜率"
        if algorithm == "rate":
            base_query = self._compiled_base_query(attrs)
            if base_query_contains_rate_function(base_query):
                errors["algorithm"] = "基础查询已包含 rate/irate/increase，不能再选速率类汇聚"

        if self._is_enum_metric(attrs):
            if algorithm in NEW_ALGORITHMS:
                errors["algorithm"] = "枚举指标不能使用新的汇聚算法"
            if compare_mode != "absolute":
                errors["compare_mode"] = "枚举指标只允许比较基准为当前值"

        period = self._get_value(attrs, "period", {}) or {}
        offset_seconds = COMPARE_OFFSET_SECONDS.get(compare_mode)
        span_fields = {
            COMPARE_MODE_OFFSET_HOURS: (
                "compare_offset_hours",
                MAX_COMPARE_OFFSET_HOURS,
                3600,
                "对照小时数",
            ),
            COMPARE_MODE_OFFSET_DAYS: (
                "compare_offset_days",
                MAX_COMPARE_OFFSET_DAYS,
                86400,
                "对照天数",
            ),
            COMPARE_MODE_BASELINE_DAYS: (
                "compare_offset_days",
                MAX_COMPARE_OFFSET_DAYS,
                None,
                "对照天数",
            ),
            COMPARE_MODE_BASELINE_WEEKS: (
                "compare_baseline_weeks",
                MAX_COMPARE_BASELINE_WEEKS,
                None,
                "对照周数",
            ),
        }
        span = span_fields.get(compare_mode)
        if span:
            field, limit, unit_seconds, label = span
            raw_span = self._get_value(attrs, field, None)
            minimum = (
                2
                if compare_mode in (COMPARE_MODE_BASELINE_WEEKS, COMPARE_MODE_BASELINE_DAYS)
                else 1
            )
            span_message = span_value_message(label, raw_span, minimum, limit)
            if span_message:
                errors[field] = span_message
            else:
                attrs[field] = raw_span
                if unit_seconds:
                    offset_seconds = raw_span * unit_seconds
                elif "compare_mode" not in errors:
                    try:
                        period_seconds = period_to_seconds(period)
                    except BaseAppException:
                        period_seconds = None
                    if compare_mode == COMPARE_MODE_BASELINE_WEEKS:
                        stride_seconds = 7 * 86400
                    else:
                        stride_seconds = 86400
                    if (
                        period_seconds
                        and period_seconds % stride_seconds == 0
                        and 1 <= period_seconds // stride_seconds <= raw_span
                    ):
                        errors["compare_mode"] = COMPARE_SPAN_CONFLICT_MESSAGE
            if "compare_mode" in attrs:
                for other, *_rest in span_fields.values():
                    if other != field:
                        attrs[other] = None
        elif "compare_mode" in attrs:
            for other, *_rest in span_fields.values():
                attrs[other] = None
        if offset_seconds:
            try:
                if period_to_seconds(period) == offset_seconds:
                    errors["compare_mode"] = COMPARE_SPAN_CONFLICT_MESSAGE
            except BaseAppException:
                logger.debug("skip compare offset equality check")

        recovery = self._get_value(attrs, "recovery_threshold", {}) or {}
        thresholds = self._get_value(attrs, "threshold", []) or []
        if recovery:
            trigger_methods = {
                item.get("method")
                for item in thresholds
                if isinstance(item, dict) and item.get("method")
            }
            recovery_method = recovery.get("method")
            if trigger_methods & HIGH_SIDE_METHODS and trigger_methods & LOW_SIDE_METHODS:
                errors["recovery_threshold"] = "多级触发方向不一致时不能配置恢复阈值"
            elif trigger_methods <= HIGH_SIDE_METHODS and trigger_methods:
                if recovery_method not in LOW_SIDE_METHODS:
                    errors["recovery_threshold"] = "恢复阈值必须在触发阈的对侧"
            elif trigger_methods <= LOW_SIDE_METHODS and trigger_methods:
                if recovery_method not in HIGH_SIDE_METHODS:
                    errors["recovery_threshold"] = "恢复阈值必须在触发阈的对侧"

        no_data_period = self._get_value(attrs, "no_data_period", {}) or {}
        no_data_recovery = self._get_value(attrs, "no_data_recovery_period", {}) or {}
        if no_data_period and no_data_recovery:
            try:
                if period_to_seconds(no_data_period) < period_to_seconds(no_data_recovery):
                    errors["no_data_period"] = "无数据检测窗不能小于恢复窗"
            except BaseAppException:
                logger.debug("skip no-data window comparison")

        if algorithm == COUNT_IF_ALGORITHM:
            predicate = self._get_value(attrs, "count_predicate", {}) or {}
            if not isinstance(predicate, dict) or "method" not in predicate or "value" not in predicate:
                errors["count_predicate"] = "条件计数必须填写内阈运算符与值"
            elif predicate.get("method") not in PREDICATE_TO_PROMQL:
                errors["count_predicate"] = "条件计数内阈运算符非法"
            else:
                raw_value = predicate.get("value")
                try:
                    if isinstance(raw_value, bool) or not math.isfinite(float(raw_value)):
                        raise ValueError
                except (TypeError, ValueError):
                    errors["count_predicate"] = "条件计数内阈必须是有限数值"

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def _get_monitor_object(self):
        """从请求数据或已有实例中获取关联的监控对象。"""
        request_data = self.initial_data if hasattr(self, "initial_data") else {}
        monitor_object_id = request_data.get("monitor_object")

        if monitor_object_id:
            from apps.monitor.models.monitor_object import MonitorObject

            try:
                return MonitorObject.objects.get(pk=monitor_object_id)
            except MonitorObject.DoesNotExist:
                return None

        if self.instance and hasattr(self.instance, "monitor_object"):
            return self.instance.monitor_object

        return None
