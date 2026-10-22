"""指标查询服务 - 负责指标数据的查询和格式化"""

import copy
import json
import math
import re

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.expression.conditions import compile_filter_to_query
from apps.monitor.expression.query import build_formula_query
from apps.monitor.models import Metric
from apps.monitor.tasks.utils.policy_methods import (
    COMPARE_MODE_ABSOLUTE,
    COMPARE_MODE_TIMELEFT,
    compile_baseline_query,
    compile_existence_query,
    compile_policy_query,
    compile_window_query,
    format_period as format_policy_period,
    period_to_seconds,
    resolve_result_unit,
)
from apps.monitor.tasks.utils.policy_multi import (
    condition_metric_items,
    condition_policy_like,
    formula_query_condition,
    is_formula_condition,
    is_multi_query,
    multi_queries,
)
from apps.monitor.utils.dimension import parse_instance_id, ScopedInstanceMatcher
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.monitor.utils.unit_converter import UnitConverter
from apps.core.logger import celery_logger as logger


def _parse_finite_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


class MetricQueryService:
    """指标查询服务

    负责:
    - 格式化PromQL/MetricQL查询语句
    - 查询聚合指标数据
    - 查询原始指标数据
    - 单位转换
    """

    def __init__(self, policy, instances_map: dict):
        """初始化指标查询服务

        Args:
            policy: 监控策略对象
            instances_map: 实例ID到实例名称的映射
        """
        self.policy = policy
        self.instances_map = instances_map
        self.instance_id_keys = None
        self.metric = None
        self.compiled_formula = None
        self._multi_metrics = None
        self._scoped_instance_matcher = ScopedInstanceMatcher(
            getattr(getattr(self.policy, "monitor_object", None), "instance_id_keys", None)
            or [],
            self.instances_map,
        )
        self._result_unit = resolve_result_unit(self.policy)
        self._unit_conversion_enabled = bool(
            self._result_unit.conversion_enabled
            and self.policy.metric_unit
            and self.policy.calculation_unit
            and self.policy.metric_unit != self.policy.calculation_unit
        )
        self._overlay_last_values = None

    def set_monitor_obj_instance_key(self):
        """设置监控对象实例标识键

        根据查询条件类型确定实例ID的组成键,用于后续数据聚合分组

        Raises:
            BaseAppException: 当metric不存在时抛出
        """
        query_type = self.policy.query_condition.get("type")

        if query_type == "pmq":
            # PMQ类型: trap采集使用source,其他使用配置的instance_id_keys
            if self.policy.collect_type == "trap":
                self.instance_id_keys = ["source"]
            else:
                self.instance_id_keys = self.policy.query_condition.get(
                    "instance_id_keys", ["instance_id"]
                )
            return

        if query_type == "formula":
            self._ensure_formula_compiled()
            return

        if query_type == "multi":
            self._load_multi_metrics()
            return

        # Metric类型: 从metric配置中获取instance_id_keys
        metric_id = self.policy.query_condition["metric_id"]
        self.metric = Metric.objects.filter(id=metric_id).first()

        if not self.metric:
            raise BaseAppException(f"metric does not exist [{metric_id}]")

        self.instance_id_keys = self.metric.instance_id_keys

    def format_period(self, period, points=1):
        """格式化周期为VictoriaMetrics查询步长格式

        Args:
            period: 周期配置 {"type": "min|hour|day", "value": int}
            points: 兼容参数，不改变步长；连续触发只扩展查询范围

        Returns:
            str: 格式化后的步长字符串,如 "5m", "1h", "1d"

        Raises:
            BaseAppException: 周期为空或类型无效
        """
        if not period:
            raise BaseAppException("policy period is empty")
        return format_policy_period(period, points)

    def format_pmq(self, base_filters=None):
        """格式化PromQL/MetricQL查询语句

        Args:
            base_filters: 注入到 ``__$labels__`` 的范围过滤条件（实例 selector）。
                为空时保持原查询语义。

        Returns:
            str: 格式化后的查询语句
        """
        query_condition = self.policy.query_condition
        query_type = query_condition.get("type")

        # 如果是PMQ类型,直接返回查询语句
        if query_type == "pmq":
            return query_condition.get("query")

        if query_type == "formula":
            if not base_filters:
                return self._ensure_formula_compiled().query
            return self._compile_scoped_formula(base_filters).query

        return compile_filter_to_query(
            self.metric.query,
            query_condition.get("filter", []),
            base_filters=base_filters or None,
        )

    def _scope_instance_id_keys(self):
        """范围下推使用的对象身份键；无法可靠映射到 label 时返回空列表。"""
        if self.policy.query_condition.get("type") not in ("metric", "formula", "multi"):
            return []
        if getattr(self.policy, "collect_type", "") == "trap":
            return []
        return list(self._scoped_instance_matcher.object_instance_id_keys)

    def _scope_batches(self, instance_ids=None):
        """把实例范围切成有界批次，每批是可注入 ``__$labels__`` 的 base_filters。

        返回 ``[None]`` 表示不下推（无范围、pmq 查询或身份无法映射），
        此时沿用 ``format_aggregation_metrics`` 的 Python 侧过滤。
        """
        keys = self._scope_instance_id_keys()
        if not keys:
            return [None]
        ordered = list(instance_ids) if instance_ids is not None else list(self.instances_map)
        if not ordered:
            return [None]

        values_by_id = {}
        for instance_id in ordered:
            values = parse_instance_id(instance_id)
            if len(values) < len(keys) or any(
                value in (None, "") for value in values[: len(keys)]
            ):
                return [None]
            values_by_id[instance_id] = values

        batch_size = AlertConstants.SCAN_SCOPE_BATCH_SIZE
        batches = []
        for start in range(0, len(ordered), batch_size):
            chunk = ordered[start : start + batch_size]
            filters = []
            for index, key in enumerate(keys):
                label_values = sorted({str(values_by_id[item][index]) for item in chunk})
                filters.append(
                    {
                        "name": key,
                        "method": "=~",
                        "value": "|".join(re.escape(value) for value in label_values),
                    }
                )
            batches.append(filters)
        return batches

    def _compile_scoped_formula(self, base_filters):
        refs = [
            item.get("ref")
            for item in self.policy.query_condition.get("queries") or []
            if item.get("ref")
        ]
        compiled = build_formula_query(
            self.policy.query_condition,
            base_filters_by_ref={ref: base_filters for ref in refs},
        )
        if self.compiled_formula is None:
            self.compiled_formula = compiled
            self.instance_id_keys = list(compiled.group_by)
        return compiled

    @staticmethod
    def _merge_range_payloads(payloads):
        merged = None
        results = []
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            if payload.get("status") not in (None, "success"):
                # 保留错误响应原样交给调用方判定，不把部分成功伪装成完整结果。
                return payload
            data = payload.get("data") or {}
            if merged is None:
                merged = {key: value for key, value in payload.items() if key != "data"}
                merged["data"] = {key: value for key, value in data.items() if key != "result"}
            results.extend(data.get("result") or [])
        if merged is None:
            return {"data": {"result": []}}
        merged["data"]["result"] = results
        return merged

    def _run_scoped_range(
        self,
        build_query,
        period,
        points=1,
        instance_ids=None,
        end_timestamp=None,
        format_base=None,
    ):
        """按实例范围分批执行 query_range 并合并结果。

        Args:
            build_query: ``(base_query, step) -> promql``
            instance_ids: 显式范围；None 表示使用策略 ``instances_map``。
            end_timestamp: 窗口右端；None 表示 ``policy.last_run_time``。
        """
        if end_timestamp is None:
            end_timestamp = int(self.policy.last_run_time.timestamp())
        period_seconds = period_to_seconds(period)
        points = max(1, int(points or 1))
        start_timestamp = end_timestamp - period_seconds * points
        step = self.format_period(period, points)

        batches = self._scope_batches(instance_ids)
        format_base = format_base or self.format_pmq
        payloads = []
        for base_filters in batches:
            query = build_query(format_base(base_filters), step)
            payload = VictoriaMetricsAPI().query_range(
                query, start_timestamp, end_timestamp, step
            )
            if len(batches) == 1:
                return payload
            payloads.append(payload)
        return self._merge_range_payloads(payloads)

    def _compiled_group_by(self):
        return ",".join(self.get_result_group_by())

    def _build_policy_query(self, base_query, step):
        return compile_policy_query(
            self.policy, base_query, step, self._compiled_group_by()
        )

    def query_comparison_metrics(self, period, points=1):
        """带 algorithm / compare_mode 变换的比较查询。"""
        if self.is_multi():
            raise BaseAppException("多指标条件需要按条件分别查询")
        return self._run_scoped_range(self._build_policy_query, period, points)

    def query_multi_comparison_metrics(self, period, points=1, instance_ids=None, end_timestamp=None):
        """每个条件各执行一次比较查询，按 ref 收集。"""
        self._ensure_multi_metrics()
        results = {}
        for condition in self.multi_conditions():
            results[condition.get("ref")] = self._query_condition_range(
                condition,
                compile_policy_query,
                period,
                points,
                instance_ids=instance_ids,
                end_timestamp=end_timestamp,
            )
        return results

    def query_multi_window_metrics(self, period, instance_ids=None, end_timestamp=None):
        """快照窗口：每个条件一条与比较查询同形的查询。"""
        if instance_ids is not None and not instance_ids:
            return {condition.get("ref"): {"data": {"result": []}} for condition in self.multi_conditions()}
        return self.query_multi_comparison_metrics(
            period, 1, instance_ids=instance_ids, end_timestamp=end_timestamp
        )

    def query_existence_metrics(self, period, points=1):
        """不带比较基准的存在性查询，供无数据检测/恢复与基线同步。"""
        if self.is_multi():
            self._ensure_multi_metrics()
            anchor = self.multi_conditions()[0]
            return self._query_condition_range(anchor, compile_existence_query, period, points)

        def build_query(base_query, step):
            return compile_existence_query(
                self.policy, base_query, step, self._compiled_group_by()
            )

        return self._run_scoped_range(build_query, period, points)

    def query_policy_window_metrics(self, period, instance_ids=None, end_timestamp=None):
        """只查给定监控实例的策略窗口结果，供快照兜底与告警前点使用。

        与 ``query_comparison_metrics`` 使用同一 PromQL 编译，回包受
        ``by (group_by)`` 与实例 selector 双重收敛；不再拉取无聚合的原始序列。
        ``instance_ids`` 为空列表时不发起查询。
        """
        if instance_ids is not None and not instance_ids:
            return {"data": {"result": []}}
        return self._run_scoped_range(
            self._build_policy_query,
            period,
            1,
            instance_ids=instance_ids,
            end_timestamp=end_timestamp,
        )

    def convert_metric_values(self, vm_data):
        """转换指标数值到计算单位

        Args:
            vm_data: VictoriaMetrics返回的数据

        Returns:
            dict: 转换后的数据（如果不需要转换则返回原数据）
        """
        if not self._unit_conversion_enabled:
            return vm_data

        # 检查单位是否可以转换
        if not UnitConverter.is_convertible(
            self.policy.metric_unit, self.policy.calculation_unit
        ):
            logger.warning(
                f"策略 {self.policy.id}: 单位 '{self.policy.metric_unit}' 和 "
                f"'{self.policy.calculation_unit}' 不属于同一体系，跳过单位转换"
            )
            return vm_data

        converted_data = copy.deepcopy(vm_data)
        try:
            # 先在副本上转换，全部成功后再返回，避免中途失败留下混合单位。
            for result in converted_data.get("data", {}).get("result", []):
                if "values" not in result:
                    continue

                # 提取所有数值（跳过时间戳）。非有限值继续留给后续扫描作为无效样本处理。
                values = [_parse_finite_float(v[1]) for v in result["values"]]
                if any(value is None for value in values):
                    continue

                # 进行单位转换
                converted_values = UnitConverter.convert_values(
                    values, self.policy.metric_unit, self.policy.calculation_unit
                )

                # 更新副本中的values
                for i, (timestamp, _) in enumerate(result["values"]):
                    result["values"][i] = [timestamp, str(converted_values[i])]

            logger.info(
                f"策略 {self.policy.id}: 成功转换指标单位 "
                f"{self.policy.metric_unit} -> {self.policy.calculation_unit}"
            )
            return converted_data

        except Exception as e:
            logger.error(f"策略 {self.policy.id}: 单位转换失败: {e}")
            return vm_data

    def get_effective_calculation_unit(self):
        """返回最终结果单位，变换后量纲由 resolve_result_unit 决定。"""
        return (
            self._result_unit.unit
            or self.policy.calculation_unit
            or self.policy.metric_unit
            or ""
        )

    def get_effective_threshold_unit(self):
        """返回阈值输入单位；结果不再是指标量纲时锁死为结果单位。"""
        if not self._result_unit.conversion_enabled:
            return self._result_unit.unit or ""
        return (
            getattr(self.policy, "threshold_unit", "")
            or self.get_effective_calculation_unit()
        )

    def convert_thresholds(self, thresholds):
        """把阈值临时副本换算到最终结果单位，不改写策略配置。"""
        converted = copy.deepcopy(thresholds)
        if not converted:
            return converted
        if not self._result_unit.conversion_enabled:
            return converted

        source_unit = self.get_effective_threshold_unit()
        target_unit = self.get_effective_calculation_unit()
        if not source_unit or not target_unit:
            return converted
        if not UnitConverter.is_convertible(source_unit, target_unit):
            raise BaseAppException(
                f"策略 {self.policy.id}: 阈值单位 '{source_unit}' "
                f"不能转换为结果单位 '{target_unit}'"
            )

        values = [float(item["value"]) for item in converted]
        converted_values = UnitConverter.convert_values(
            values, source_unit, target_unit
        )
        for item, value in zip(converted, converted_values):
            item["value"] = value
        return converted

    def get_display_unit(self):
        """获取用于展示的单位

        Returns:
            str: 展示单位
        """
        unit = self.get_effective_calculation_unit()
        return UnitConverter.get_display_unit(unit) if unit else ""

    def is_metric_unit_converted(self) -> bool:
        """扫描侧是否已把采集值换算到 calculation_unit。"""
        return self._unit_conversion_enabled

    def get_source_display_unit(self):
        unit = self.policy.calculation_unit or self.policy.metric_unit or ""
        return UnitConverter.get_display_unit(unit) if unit else ""

    def query_overlay_last_values(self):
        if self._overlay_last_values is None:
            self._overlay_last_values = self._load_overlay_last_values()
        return self._overlay_last_values

    def _load_overlay_last_values(self):
        compare_mode = getattr(self.policy, "compare_mode", None) or COMPARE_MODE_ABSOLUTE
        if compare_mode in ("", COMPARE_MODE_ABSOLUTE):
            return {}, {}
        group_by = self._compiled_group_by()

        def build_current(base_query, step):
            return compile_window_query(self.policy, base_query, step, group_by)

        def build_baseline(base_query, step):
            return compile_baseline_query(self.policy, base_query, step, group_by)

        current_data = self.convert_metric_values(
            self._run_scoped_range(build_current, self.policy.period, 1)
        )
        current_map = self._last_numeric_map(current_data)
        if compare_mode == COMPARE_MODE_TIMELEFT:
            return current_map, {}
        baseline_data = self.convert_metric_values(
            self._run_scoped_range(build_baseline, self.policy.period, 1)
        )
        return current_map, self._last_numeric_map(baseline_data)

    def _last_numeric_map(self, vm_data):
        formatted = self.format_aggregation_metrics(vm_data)
        return {
            key: item["value"]
            for key, item in formatted.items()
            if item.get("value") is not None
        }

    def get_enum_value_map(self) -> dict:
        """获取枚举类型指标的值到名称的映射

        Returns:
            dict: {枚举值(int): 枚举名称(str)} 的映射，非枚举类型返回空字典
        """
        if not self.metric:
            return {}

        if self.metric.data_type != "Enum":
            return {}

        try:
            enum_list = json.loads(self.metric.unit)
            return {
                item["id"]: item["name"]
                for item in enum_list
                if "id" in item and "name" in item
            }
        except (json.JSONDecodeError, TypeError, KeyError):
            return {}

    def is_enum_metric(self) -> bool:
        """判断当前指标是否为枚举类型

        Returns:
            bool: 是否为枚举类型
        """
        return self.metric is not None and self.metric.data_type == "Enum"

    def format_aggregation_metrics(self, metrics):
        """格式化聚合指标数据

        Args:
            metrics: VictoriaMetrics返回的原始指标数据

        Returns:
            dict: 格式化后的指标数据 {metric_instance_id: {"value": float, "raw_data": dict}}
        """
        result = {}
        group_by_keys = self.get_result_group_by()

        for metric_info in metrics.get("data", {}).get("result", []):
            instance_id_tuple = tuple(
                [metric_info["metric"].get(key) for key in group_by_keys]
            )
            metric_instance_id = str(instance_id_tuple)

            if self.instances_map:
                monitor_instance_id = self.get_monitor_instance_id_from_tuple(
                    instance_id_tuple, group_by_keys
                )
                if monitor_instance_id not in self.instances_map:
                    continue

            value = metric_info["values"][-1]
            parsed_value = _parse_finite_float(value[1])
            if parsed_value is None:
                continue
            result[metric_instance_id] = {
                "value": parsed_value,
                "raw_data": metric_info,
            }

        return result

    def _ensure_formula_compiled(self):
        if self.compiled_formula is None:
            self.compiled_formula = build_formula_query(self.policy.query_condition)
            self.instance_id_keys = list(self.compiled_formula.group_by)
        return self.compiled_formula

    def is_multi(self) -> bool:
        return is_multi_query(getattr(self.policy, "query_condition", None) or {})

    def multi_conditions(self) -> list[dict]:
        return multi_queries(getattr(self.policy, "query_condition", None) or {})

    def _ensure_multi_metrics(self):
        if self._multi_metrics is None:
            self._load_multi_metrics()
        return self._multi_metrics

    def _load_multi_metrics(self):
        conditions = self.multi_conditions()
        metric_ids = []
        for condition in conditions:
            metric_ids.extend(item.get("metric_id") for item in condition_metric_items(condition))
        metrics = {item.id: item for item in Metric.objects.filter(id__in=metric_ids)}
        missing = [metric_id for metric_id in metric_ids if metric_id not in metrics]
        if missing:
            raise BaseAppException(f"metric does not exist [{missing[0]}]")
        self._multi_metrics = metrics
        anchor = conditions[0] if conditions else {}
        if is_formula_condition(anchor):
            operands = condition_metric_items(anchor)
            first_id = operands[0].get("metric_id") if operands else None
            self.metric = metrics.get(first_id)
        else:
            self.metric = metrics.get(anchor.get("metric_id"))
        self.instance_id_keys = list(anchor.get("group_by") or [])
        return metrics

    def _query_condition_range(
        self,
        condition,
        compile_fn,
        period,
        points=1,
        instance_ids=None,
        end_timestamp=None,
    ):
        metrics = self._ensure_multi_metrics()
        metric = None
        if not is_formula_condition(condition):
            metric = metrics.get(condition.get("metric_id"))
            if metric is None:
                raise BaseAppException(f"metric does not exist [{condition.get('metric_id')}]")
        policy_like = condition_policy_like(self.policy, condition)
        group_by = ",".join(condition.get("group_by") or [])

        def format_base(base_filters, metric=metric, condition=condition):
            if is_formula_condition(condition):
                operands = condition_metric_items(condition)
                compiled = build_formula_query(
                    formula_query_condition(condition),
                    base_filters_by_ref={
                        item.get("ref"): base_filters or []
                        for item in operands
                        if item.get("ref")
                    },
                )
                return compiled.query
            return compile_filter_to_query(
                metric.query or "",
                condition.get("filter") or [],
                base_filters=base_filters or None,
            )

        def build_query(base_query, step, policy_like=policy_like, group_by=group_by):
            return compile_fn(policy_like, base_query, step, group_by)

        return self._run_scoped_range(
            build_query,
            period,
            points,
            instance_ids=instance_ids,
            end_timestamp=end_timestamp,
            format_base=format_base,
        )

    def convert_condition_values(self, vm_data, condition):
        """按该条件自己的单位换算序列副本，不改策略配置。"""
        policy_like = condition_policy_like(self.policy, condition)
        result_unit = resolve_result_unit(policy_like)
        metric_unit = condition.get("metric_unit") or ""
        calculation_unit = condition.get("calculation_unit") or ""
        if (
            not result_unit.conversion_enabled
            or not metric_unit
            or not calculation_unit
            or metric_unit == calculation_unit
        ):
            return vm_data
        if not UnitConverter.is_convertible(metric_unit, calculation_unit):
            raise BaseAppException(
                f"策略 {getattr(self.policy, 'id', '')}: 条件 {condition.get('ref')} "
                f"单位 '{metric_unit}' 不能转换为 '{calculation_unit}'"
            )
        converted_data = copy.deepcopy(vm_data)
        for result in converted_data.get("data", {}).get("result", []):
            if "values" not in result:
                continue
            values = [_parse_finite_float(item[1]) for item in result["values"]]
            if any(value is None for value in values):
                continue
            converted_values = UnitConverter.convert_values(values, metric_unit, calculation_unit)
            for index, (timestamp, _) in enumerate(result["values"]):
                result["values"][index] = [timestamp, str(converted_values[index])]
        return converted_data

    def convert_condition_thresholds(self, condition):
        """按该条件自己的阈值单位换算副本，不改写 queries[]。"""
        converted = copy.deepcopy(condition.get("threshold") or [])
        if not converted:
            return converted
        policy_like = condition_policy_like(self.policy, condition)
        result_unit = resolve_result_unit(policy_like)
        if not result_unit.conversion_enabled:
            return converted
        source_unit = condition.get("threshold_unit") or result_unit.unit or ""
        target_unit = result_unit.unit or condition.get("calculation_unit") or ""
        if not source_unit or not target_unit or source_unit == target_unit:
            return converted
        if not UnitConverter.is_convertible(source_unit, target_unit):
            raise BaseAppException(
                f"策略 {getattr(self.policy, 'id', '')}: 条件 {condition.get('ref')} "
                f"阈值单位 '{source_unit}' 不能转换为 '{target_unit}'"
            )
        values = [float(item["value"]) for item in converted]
        converted_values = UnitConverter.convert_values(values, source_unit, target_unit)
        for item, value in zip(converted, converted_values):
            item["value"] = value
        return converted

    def condition_with_converted_thresholds(self, condition):
        copied = dict(condition)
        copied["threshold"] = self.convert_condition_thresholds(condition)
        return copied

    def condition_result_unit(self, condition) -> str:
        result_unit = resolve_result_unit(condition_policy_like(self.policy, condition))
        return result_unit.unit or condition.get("calculation_unit") or condition.get("metric_unit") or ""

    def condition_display_unit(self, condition) -> str:
        unit = self.condition_result_unit(condition)
        return UnitConverter.get_display_unit(unit) if unit else ""

    def condition_enum_map(self, condition) -> dict:
        if is_formula_condition(condition):
            return {}
        metric = (self._multi_metrics or {}).get(condition.get("metric_id"))
        if metric is None or getattr(metric, "data_type", "") != "Enum":
            return {}
        try:
            enum_list = json.loads(metric.unit)
        except (json.JSONDecodeError, TypeError):
            return {}
        return {item["id"]: item["name"] for item in enum_list if isinstance(item, dict) and "id" in item and "name" in item}

    def condition_metric_name(self, condition) -> str:
        if is_formula_condition(condition):
            name = str(condition.get("metric_name") or "").strip()
            return name or str(condition.get("ref") or "")
        metric = (self._multi_metrics or {}).get(condition.get("metric_id"))
        if metric is None:
            return str(condition.get("ref") or "")
        return metric.display_name or metric.name or str(condition.get("ref") or "")

    def get_result_group_by(self) -> list:
        query = self.policy.query_condition or {}
        if query.get("type") == "formula":
            return list(self._ensure_formula_compiled().group_by)
        if query.get("type") == "multi":
            conditions = self.multi_conditions()
            if not conditions:
                return []
            return list(conditions[0].get("group_by") or [])
        return self.policy.group_by or []

    def get_monitor_instance_id_key(self) -> str:
        result_group_by = self.get_result_group_by()
        if getattr(self.policy, "collect_type", "") == "trap":
            return "source"
        if "instance_id" in result_group_by:
            return "instance_id"
        metric_instance_keys = getattr(self.metric, "instance_id_keys", None) or []
        if metric_instance_keys:
            return metric_instance_keys[0]
        query_instance_keys = self.policy.query_condition.get("instance_id_keys") or []
        if query_instance_keys:
            return query_instance_keys[0]
        return result_group_by[0] if result_group_by else ""

    def get_monitor_instance_id_from_tuple(
        self, instance_id_tuple: tuple, group_by_keys: list | None = None
    ) -> str:
        if not instance_id_tuple:
            return ""

        group_by_keys = group_by_keys or self.get_result_group_by()
        scoped_instance_id = self._scoped_instance_matcher.resolve(
            instance_id_tuple, group_by_keys
        )
        if scoped_instance_id:
            return scoped_instance_id

        monitor_key = self.get_monitor_instance_id_key()
        if monitor_key in group_by_keys:
            index = group_by_keys.index(monitor_key)
            if index < len(instance_id_tuple):
                return str((instance_id_tuple[index],))

        return str((instance_id_tuple[0],))

    def get_monitor_instance_id_from_metric_instance_id(
        self, metric_instance_id: str
    ) -> str:
        return self.get_monitor_instance_id_from_tuple(parse_instance_id(metric_instance_id))
