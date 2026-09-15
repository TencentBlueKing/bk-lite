"""指标查询服务 - 负责指标数据的查询和格式化"""

import copy
import json
import math

from apps.core.exceptions.base_app_exception import BaseAppException
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

    def format_pmq(self):
        """格式化PromQL/MetricQL查询语句

        Returns:
            str: 格式化后的查询语句
        """
        query_condition = self.policy.query_condition
        query_type = query_condition.get("type")

        # 如果是PMQ类型,直接返回查询语句
        if query_type == "pmq":
            return query_condition.get("query")

        if query_type == "formula":
            return self._ensure_formula_compiled().query

        return compile_filter_to_query(self.metric.query, query_condition.get("filter", []))

    def _query_range(self, query, period, points=1):
        end_timestamp = int(self.policy.last_run_time.timestamp())
        period_seconds = period_to_seconds(period)
        points = max(1, int(points or 1))
        start_timestamp = end_timestamp - period_seconds * points
        step = self.format_period(period, points)
        return VictoriaMetricsAPI().query_range(
            query, start_timestamp, end_timestamp, step
        )

    def _compiled_group_by(self):
        return ",".join(self.get_result_group_by())

    def query_comparison_metrics(self, period, points=1):
        """带 algorithm / compare_mode 变换的比较查询。"""
        step = self.format_period(period, points)
        query = compile_policy_query(
            self.policy,
            self.format_pmq(),
            step,
            self._compiled_group_by(),
        )
        return self._query_range(query, period, points)

    def query_existence_metrics(self, period, points=1):
        """不带比较基准的存在性查询，供无数据检测/恢复与基线同步。"""
        step = self.format_period(period, points)
        query = compile_existence_query(
            self.policy,
            self.format_pmq(),
            step,
            self._compiled_group_by(),
        )
        return self._query_range(query, period, points)

    def query_raw_metrics(self, period, points=1):
        """查询原始指标数据(不进行聚合)

        Args:
            period: 周期配置
            points: 数据点数

        Returns:
            dict: VictoriaMetrics返回的原始指标数据
        """
        # 计算查询时间范围
        end_timestamp = int(self.policy.last_run_time.timestamp())
        period_seconds = period_to_seconds(period)
        start_timestamp = end_timestamp - period_seconds

        # 准备查询参数
        query = self.format_pmq()
        step = self.format_period(period, points)

        # 直接查询原始数据
        raw_metrics = VictoriaMetricsAPI().query_range(
            query, start_timestamp, end_timestamp, step
        )
        return raw_metrics

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

        try:
            # 遍历所有result，转换values中的数值
            for result in vm_data.get("data", {}).get("result", []):
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

                # 更新result中的values
                for i, (timestamp, _) in enumerate(result["values"]):
                    result["values"][i] = [timestamp, str(converted_values[i])]

            logger.info(
                f"策略 {self.policy.id}: 成功转换指标单位 "
                f"{self.policy.metric_unit} -> {self.policy.calculation_unit}"
            )

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
        step = self.format_period(self.policy.period, 1)
        base_query = self.format_pmq()
        group_by = self._compiled_group_by()
        current_query = compile_window_query(self.policy, base_query, step, group_by)
        current_data = self.convert_metric_values(
            self._query_range(current_query, self.policy.period, 1)
        )
        current_map = self._last_numeric_map(current_data)
        if compare_mode == COMPARE_MODE_TIMELEFT:
            return current_map, {}
        baseline_query = compile_baseline_query(self.policy, base_query, step, group_by)
        baseline_data = self.convert_metric_values(
            self._query_range(baseline_query, self.policy.period, 1)
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

    def get_result_group_by(self) -> list:
        if self.policy.query_condition.get("type") == "formula":
            return list(self._ensure_formula_compiled().group_by)
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
