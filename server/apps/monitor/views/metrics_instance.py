from typing import Optional

from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException, ValidationAppException
from apps.core.logger import monitor_logger as logger
from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.models import MonitorInstance
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.services.authorized_metric_query import AuthorizedMetricQueryError, AuthorizedMetricQueryService
from apps.monitor.services.metrics import Metrics as MetricsService
from apps.monitor.services.metrics import MetricsQueryBudgetExceeded
from apps.monitor.utils.unit_converter import UnitConverter


class MetricsInstanceViewSet(viewsets.ViewSet):
    @staticmethod
    def _authorized_query_service(request):
        current_team = get_current_team(request)
        if current_team in (None, ""):
            raise BaseAppException("current_team is required")
        return AuthorizedMetricQueryService(
            user=request.user,
            current_team=current_team,
            include_children=request.COOKIES.get("include_children", "0") == "1",
        )

    @staticmethod
    def _raise_authorized_query_error(exc: AuthorizedMetricQueryError):
        if exc.code in {"monitor_instance_forbidden", "query_identity_required"}:
            raise UnauthorizedException(str(exc))
        raise ValidationAppException(str(exc))

    @action(methods=["post"], detail=False, url_path="query_by_metric_range")
    def query_by_metric_range(self, request):
        """按当前用户实例权限执行服务端指标模板的范围查询。"""
        try:
            data = self._authorized_query_service(request).query_range(request.data)
        except AuthorizedMetricQueryError as exc:
            self._raise_authorized_query_error(exc)
        except MetricsQueryBudgetExceeded as exc:
            return WebUtils.response_error(
                response_data=exc.data,
                error_message=exc.message,
                status_code=exc.STATUS_CODE,
            )

        source_unit = request.data.get("source_unit")
        target_unit = request.data.get("unit")
        auto_convert = request.data.get("auto_convert_unit", True)
        if isinstance(auto_convert, str):
            auto_convert = auto_convert.lower() == "true"
        if source_unit:
            if target_unit:
                data = self._apply_unit_conversion(data, source_unit, target_unit)
            elif auto_convert:
                data = self._apply_unit_conversion(data, source_unit)
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="query_by_metric")
    def query_by_metric(self, request):
        """按当前用户实例权限执行服务端指标模板的即时查询。"""
        try:
            data = self._authorized_query_service(request).query_instant(request.data)
        except AuthorizedMetricQueryError as exc:
            self._raise_authorized_query_error(exc)

        source_unit = request.data.get("source_unit")
        target_unit = request.data.get("unit")
        auto_convert = request.data.get("auto_convert_unit", True)
        if isinstance(auto_convert, str):
            auto_convert = auto_convert.lower() == "true"
        if source_unit:
            if target_unit:
                data = self._apply_unit_conversion(data, source_unit, target_unit)
            elif auto_convert:
                data = self._apply_unit_conversion(data, source_unit)
        return WebUtils.response_success(data)

    @staticmethod
    def _apply_unit_conversion(response_data: dict, source_unit: str, target_unit: Optional[str] = None) -> dict:
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

            logger.debug(f"开始单位转换，初始单位: {source_unit}, 目标单位: {target_unit or '自动'}")

            all_numeric_values = []

            for item in result_list:
                values = item.get("values") or item.get("value")
                if not values:
                    continue

                extracted_values = MetricsInstanceViewSet._extract_values_from_item(values)
                all_numeric_values.extend(extracted_values)

            if not all_numeric_values:
                logger.debug("没有找到有效的数值，跳过单位转换")
                return response_data

            if target_unit:
                final_target_unit = target_unit
            else:
                _, final_target_unit = UnitConverter.auto_convert(all_numeric_values, source_unit)

            logger.info(f"统一单位转换: {source_unit} -> {final_target_unit}, 基于 {len(all_numeric_values)} 个数据点, 涉及 {len(result_list)} 条时间序列")

            for item in result_list:
                values = item.get("values") or item.get("value")
                if not values:
                    continue

                is_single_value = isinstance(values, list) and len(values) == 2 and not isinstance(values[0], list)

                if is_single_value:
                    MetricsInstanceViewSet._convert_single_value(item, values, source_unit, final_target_unit)
                else:
                    MetricsInstanceViewSet._convert_range_values(item, values, source_unit, final_target_unit)

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
        is_single_value = isinstance(values, list) and len(values) == 2 and not isinstance(values[0], list)

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
    def _convert_single_value(item: dict, values: list, source_unit: str, target_unit: str):
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
            converted_values = UnitConverter.convert_values([value], source_unit, target_unit)
            item["value"] = [timestamp, str(converted_values[0])]

            logger.debug(f"转换: {item.get('metric', {}).get('__name__', 'unknown')} {value} {source_unit} -> {converted_values[0]} {target_unit}")
        except (ValueError, TypeError) as e:
            logger.warning(f"无法转换值 '{value_str}': {e}")

    @staticmethod
    def _convert_range_values(item: dict, values: list, source_unit: str, target_unit: str):
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
        converted_values = UnitConverter.convert_values(numeric_values, source_unit, target_unit)

        # 更新转换后的值
        for idx, converted_value in zip(valid_indices, converted_values):
            values[idx][1] = str(converted_value)

        logger.debug(f"转换: {item.get('metric', {}).get('__name__', 'unknown')} {len(converted_values)} 个数据点 -> {target_unit}")

    @action(methods=["get"], detail=False, url_path="query_by_instance")
    def query_by_instance(self, request):
        monitor_object_id = request.GET.get("monitor_object_id")
        metric_id = request.GET.get("metric_id")
        instance_id = request.GET.get("instance_id")
        auto_convert = request.GET.get("auto_convert_unit", "true").lower() == "true"

        if not all([monitor_object_id, metric_id, instance_id]):
            raise BaseAppException("monitor_object_id, metric_id, instance_id are required")

        current_team = get_current_team(request)
        include_children = request.COOKIES.get("include_children", "0") == "1"

        if not request.user.is_superuser:
            permission = get_permission_rules(
                request.user,
                current_team,
                "monitor",
                f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
                include_children=include_children,
            )
            authorized_qs = permission_filter(
                MonitorInstance,
                permission,
                team_key="monitorinstanceorganization__organization__in",
                id_key="id__in",
            ).filter(id=instance_id)
            if not authorized_qs.exists():
                raise UnauthorizedException("无权访问该监控实例")

        metric = Metric.objects.filter(id=metric_id, monitor_object_id=monitor_object_id).select_related("monitor_object").first()
        if not metric:
            raise BaseAppException("Metric not found")

        effective_instance_id_keys = MetricsService.get_effective_metric_instance_id_keys(metric)

        series_limit = request.GET.get("limit")
        series_mode = request.GET.get("mode")
        # 列表维度预览与指标卡共用通用序列预算；不读 per-metric view_config。
        if series_limit is None and metric.dimensions:
            series_limit = MetricsService.CARD_QUERY_MAX_SERIES
            series_mode = series_mode or "limited"

        preview_limit = None
        try:
            preview_limit = int(series_limit) if series_limit is not None else None
        except (TypeError, ValueError):
            preview_limit = None

        # 多取 1 条用于判断是否截断。
        fetch_limit = preview_limit + 1 if preview_limit and preview_limit > 0 else series_limit

        data = MetricsService.query_metric_by_instance(
            metric_query=metric.query,
            instance_id=instance_id,
            instance_id_keys=effective_instance_id_keys,
            dimensions=metric.dimensions,
            series_limit=fetch_limit,
            series_mode=series_mode or "limited",
        )

        if auto_convert and metric.unit:
            data = self._apply_unit_conversion(data, metric.unit)

        if preview_limit and preview_limit > 0:
            result = (data.get("data") or {}).get("result") or []
            truncated = len(result) > preview_limit
            if truncated:
                data.setdefault("data", {})["result"] = result[:preview_limit]
            data.setdefault("data", {})["series_budget"] = {
                "truncated": truncated,
                "limit": preview_limit,
                "applied": True,
            }

        return WebUtils.response_success(data)
