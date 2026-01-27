"""指标查询服务 - 负责指标数据的查询和格式化"""

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import Metric
from apps.monitor.tasks.utils.metric_query import format_to_vm_filter
from apps.monitor.tasks.utils.policy_methods import METHOD, period_to_seconds
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI
from apps.monitor.utils.unit_converter import UnitConverter
from apps.core.logger import celery_logger as logger


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
        # 单位转换配置
        self._unit_conversion_enabled = bool(
            self.policy.metric_unit
            and self.policy.calculation_unit
            and self.policy.metric_unit != self.policy.calculation_unit
        )

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
            points: 数据点数,默认为1

        Returns:
            str: 格式化后的步长字符串,如 "5m", "1h", "1d"

        Raises:
            BaseAppException: 周期为空或类型无效
        """
        if not period:
            raise BaseAppException("policy period is empty")

        period_type = period["type"]
        period_value = int(period["value"] / points)

        period_unit_map = {
            "min": "m",
            "hour": "h",
            "day": "d",
        }

        if period_type not in period_unit_map:
            raise BaseAppException(f"invalid period type: {period_type}")

        return f"{period_value}{period_unit_map[period_type]}"

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

        # 否则基于metric构建查询
        query = self.metric.query
        filter_list = query_condition.get("filter", [])
        vm_filter_str = format_to_vm_filter(filter_list)

        # 清理filter字符串尾部的逗号
        if vm_filter_str and vm_filter_str.endswith(","):
            vm_filter_str = vm_filter_str[:-1]

        # 替换查询模板中的label占位符
        query = query.replace("__$labels__", vm_filter_str or "")
        return query

    def query_aggregation_metrics(self, period, points=1):
        """查询聚合指标数据

        Args:
            period: 周期配置
            points: 数据点数

        Returns:
            dict: VictoriaMetrics返回的指标数据

        Raises:
            BaseAppException: 算法方法无效时抛出
        """
        # 计算查询时间范围
        end_timestamp = int(self.policy.last_run_time.timestamp())
        period_seconds = period_to_seconds(period)
        start_timestamp = end_timestamp - period_seconds

        # 准备查询参数
        query = self.format_pmq()
        step = self.format_period(period, points)
        group_by = ",".join(self.instance_id_keys)

        # 获取聚合方法
        method = METHOD.get(self.policy.algorithm)
        if not method:
            raise BaseAppException(f"invalid algorithm method: {self.policy.algorithm}")

        return method(query, start_timestamp, end_timestamp, step, group_by)

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

                # 提取所有数值（跳过时间戳）
                values = [float(v[1]) for v in result["values"]]

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

    def get_display_unit(self):
        """获取用于展示的单位

        Returns:
            str: 展示单位
        """
        if self._unit_conversion_enabled:
            return UnitConverter.get_display_unit(self.policy.calculation_unit)
        elif self.policy.metric_unit:
            return UnitConverter.get_display_unit(self.policy.metric_unit)
        else:
            return ""

    def format_aggregation_metrics(self, metrics):
        """格式化聚合指标数据

        Args:
            metrics: VictoriaMetrics返回的原始指标数据

        Returns:
            dict: 格式化后的指标数据 {metric_instance_id: {"value": float, "raw_data": dict}}
        """
        result = {}

        for metric_info in metrics.get("data", {}).get("result", []):
            instance_id_tuple = tuple(
                [metric_info["metric"].get(key) for key in self.instance_id_keys]
            )
            metric_instance_id = str(instance_id_tuple)

            if self.instances_map:
                monitor_instance_id = (
                    str(instance_id_tuple[0]) if instance_id_tuple else ""
                )
                if monitor_instance_id not in self.instances_map:
                    continue

            value = metric_info["values"][-1]
            result[metric_instance_id] = {
                "value": float(value[1]),
                "raw_data": metric_info,
            }

        return result
