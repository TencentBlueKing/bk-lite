from typing import Optional

from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.web_utils import WebUtils
from apps.core.logger import monitor_logger as logger
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.services.metrics import Metrics as MetricsService
from apps.monitor.utils.unit_converter import UnitConverter


class MetricsInstanceVieSet(viewsets.ViewSet):
    @action(methods=["get"], detail=False, url_path="query")
    def get_metrics(self, request):
        """
        查询指标信息（即时查询）

        Query Parameters:
            query (str): PromQL 查询语句
            source_unit (str): 初始单位（必填），如 'B', 'bytes', 'ms', 's' 等
            unit (str): 指定目标单位，若提供则直接转换到该单位，不使用自动推荐
            auto_convert_unit (bool): 是否自动转换单位，默认 True（仅在未指定 unit 时生效）
        """
        query = request.GET.get("query")
        source_unit = request.GET.get("source_unit")
        target_unit = request.GET.get("unit")
        auto_convert = request.GET.get("auto_convert_unit", "true").lower() == "true"

        data = MetricsService.get_metrics(query)

        if source_unit:
            if target_unit:
                data = self._apply_unit_conversion(data, source_unit, target_unit)
            elif auto_convert:
                data = self._apply_unit_conversion(data, source_unit)

        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="query_range")
    def get_metrics_range(self, request):
        """
        查询指标（范围查询）

        Query Parameters:
            query (str): PromQL 查询语句
            start (int): 开始时间戳（毫秒）
            end (int): 结束时间戳（毫秒）
            step (str): 查询步长，如 '5m'
            source_unit (str): 初始单位（必填），如 'B', 'bytes', 'ms', 's' 等
            unit (str): 指定目标单位，若提供则直接转换到该单位，不使用自动推荐
            auto_convert_unit (bool): 是否自动转换单位，默认 True（仅在未指定 unit 时生效）
        """
        query = request.GET.get("query")
        start = request.GET.get("start")
        end = request.GET.get("end")
        step = request.GET.get("step")
        source_unit = request.GET.get("source_unit")
        target_unit = request.GET.get("unit")
        auto_convert = request.GET.get("auto_convert_unit", "true").lower() == "true"

        data = MetricsService.get_metrics_range(query, start, end, step)

        if source_unit:
            if target_unit:
                data = self._apply_unit_conversion(data, source_unit, target_unit)
            elif auto_convert:
                data = self._apply_unit_conversion(data, source_unit)

        return WebUtils.response_success(data)

    @staticmethod
    def _apply_unit_conversion(
        response_data: dict, source_unit: str, target_unit: Optional[str] = None
    ) -> dict:
        """
        对 VictoriaMetrics 响应数据应用单位转换

        :param response_data: VictoriaMetrics API 响应数据
        :param source_unit: 前端传递的初始单位（如 'B', 'bytes', 'ms' 等）
        :param target_unit: 目标单位，若为 None 则自动推荐
        :return: 转换后的数据
        """
        try:
            if response_data.get("status") != "success":
                return response_data

            data = response_data.get("data", {})
            result_list = data.get("result", [])

            if not result_list:
                return response_data

            logger.debug(
                f"开始单位转换，初始单位: {source_unit}, 目标单位: {target_unit or '自动'}"
            )

            all_numeric_values = []

            for item in result_list:
                values = item.get("values") or item.get("value")
                if not values:
                    continue

                extracted_values = MetricsInstanceVieSet._extract_values_from_item(
                    values
                )
                all_numeric_values.extend(extracted_values)

            if not all_numeric_values:
                logger.debug("没有找到有效的数值，跳过单位转换")
                return response_data

            if target_unit:
                final_target_unit = target_unit
            else:
                _, final_target_unit = UnitConverter.auto_convert(
                    all_numeric_values, source_unit
                )

            logger.info(
                f"统一单位转换: {source_unit} -> {final_target_unit}, "
                f"基于 {len(all_numeric_values)} 个数据点, "
                f"涉及 {len(result_list)} 条时间序列"
            )

            for item in result_list:
                values = item.get("values") or item.get("value")
                if not values:
                    continue

                is_single_value = (
                    isinstance(values, list)
                    and len(values) == 2
                    and not isinstance(values[0], list)
                )

                if is_single_value:
                    MetricsInstanceVieSet._convert_single_value(
                        item, values, source_unit, final_target_unit
                    )
                else:
                    MetricsInstanceVieSet._convert_range_values(
                        item, values, source_unit, final_target_unit
                    )

            data["unit"] = final_target_unit
            data["source_unit"] = source_unit

            return response_data

        except Exception as e:
            logger.error(f"单位转换时发生错误: {e}", exc_info=True)
            return response_data

    @staticmethod
    def _extract_values_from_item(values) -> list:
        """
        从 values 中提取所有有效的数值

        :param values: 可能是单值 [timestamp, value] 或多值 [[timestamp, value], ...]
        :return: 数值列表
        """
        numeric_values = []
        is_single_value = (
            isinstance(values, list)
            and len(values) == 2
            and not isinstance(values[0], list)
        )

        if is_single_value:
            # 单值
            _, value_str = values
            if value_str is not None:
                try:
                    numeric_values.append(float(value_str))
                except (ValueError, TypeError):
                    pass
        else:
            # 范围查询
            for point in values:
                if point is None or len(point) < 2:
                    continue
                value_str = point[1]
                if value_str is not None:
                    try:
                        numeric_values.append(float(value_str))
                    except (ValueError, TypeError):
                        pass

        return numeric_values

    @staticmethod
    def _convert_single_value(
        item: dict, values: list, source_unit: str, target_unit: str
    ):
        """
        转换单值查询的数据

        :param item: 时间序列项
        :param values: [timestamp, value] 格式
        :param source_unit: 源单位
        :param target_unit: 目标单位
        """
        timestamp, value_str = values
        if value_str is None:
            return

        try:
            value = float(value_str)
            converted_values = UnitConverter.convert_values(
                [value], source_unit, target_unit
            )
            item["value"] = [timestamp, str(converted_values[0])]

            logger.debug(
                f"转换: {item.get('metric', {}).get('__name__', 'unknown')} "
                f"{value} {source_unit} -> {converted_values[0]} {target_unit}"
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"无法转换值 '{value_str}': {e}")

    @staticmethod
    def _convert_range_values(
        item: dict, values: list, source_unit: str, target_unit: str
    ):
        """
        转换范围查询的数据

        :param item: 时间序列项
        :param values: [[timestamp, value], ...] 格式
        :param source_unit: 源单位
        :param target_unit: 目标单位
        """
        numeric_values = []
        valid_indices = []

        for idx, point in enumerate(values):
            if point is None or len(point) < 2:
                continue

            value_str = point[1]
            if value_str is None:
                continue

            try:
                numeric_values.append(float(value_str))
                valid_indices.append(idx)
            except (ValueError, TypeError):
                continue

        if not numeric_values:
            return

        # 转换到统一单位
        converted_values = UnitConverter.convert_values(
            numeric_values, source_unit, target_unit
        )

        # 更新转换后的值
        for idx, converted_value in zip(valid_indices, converted_values):
            values[idx][1] = str(converted_value)

        logger.debug(
            f"转换: {item.get('metric', {}).get('__name__', 'unknown')} "
            f"{len(converted_values)} 个数据点 -> {target_unit}"
        )

    @action(methods=["get"], detail=False, url_path="query_by_instance")
    def query_by_instance(self, request):
        monitor_object_id = request.GET.get("monitor_object_id")
        metric_id = request.GET.get("metric_id")
        instance_id = request.GET.get("instance_id")
        auto_convert = request.GET.get("auto_convert_unit", "true").lower() == "true"

        if not all([monitor_object_id, metric_id, instance_id]):
            raise BaseAppException(
                "monitor_object_id, metric_id, instance_id are required"
            )

        metric = Metric.objects.filter(
            id=metric_id, monitor_object_id=monitor_object_id
        ).first()
        if not metric:
            raise BaseAppException("Metric not found")

        data = MetricsService.query_metric_by_instance(
            metric_query=metric.query,
            instance_id=instance_id,
            instance_id_keys=metric.instance_id_keys,
            dimensions=metric.dimensions,
        )

        if auto_convert and metric.unit:
            data = self._apply_unit_conversion(data, metric.unit)

        return WebUtils.response_success(data)
