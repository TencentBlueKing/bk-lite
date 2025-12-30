"""
单位管理相关视图
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from apps.core.utils.web_utils import WebUtils
from apps.monitor.serializers.unit import (
    UnitSerializer,
    UnitSystemSerializer,
    UnitConversionRequestSerializer,
    UnitConversionResponseSerializer,
    UnitSuggestionRequestSerializer,
    UnitSuggestionResponseSerializer,
)
from apps.monitor.utils.unit_converter import UnitConverter
from apps.core.logger import monitor_logger as logger


class UnitViewSet(viewsets.ViewSet):
    """
    单位管理视图集

    提供单位列表、单位转换、单位建议等功能
    """

    @extend_schema(
        summary="获取所有单位列表",
        description="返回系统支持的所有单位，包括单位ID、名称、体系、展示格式等信息",
        responses={200: UnitSerializer(many=True)},
    )
    @action(methods=['GET'], detail=False, url_path='list')
    def list_units(self, request):
        """获取所有单位列表"""
        try:
            units = UnitConverter.get_all_units()
            serializer = UnitSerializer(units, many=True)
            return WebUtils.response_success(serializer.data)
        except Exception as e:
            logger.error(f"获取单位列表失败: {e}")
            return WebUtils.response_error(f"获取单位列表失败: {str(e)}")

    @extend_schema(
        summary="按体系获取单位",
        description="按单位体系分组返回单位列表",
        parameters=[
            OpenApiParameter(
                name='system',
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="体系名称（可选），如 'percent', 'count', 'data_bytes' 等。不传则返回所有体系的单位"
            ),
        ],
        responses={200: UnitSystemSerializer(many=True)},
    )
    @action(methods=['GET'], detail=False, url_path='by-system')
    def list_by_system(self, request):
        """按体系获取单位列表"""
        try:
            system_name = request.query_params.get('system')

            if system_name:
                # 返回指定体系的单位
                units = UnitConverter.get_units_by_system(system_name)
                serializer = UnitSerializer(units, many=True)
                return WebUtils.response_success(serializer.data)
            else:
                # 按体系分组返回
                grouped_units = UnitConverter.get_units_by_system()

                # 体系描述映射
                system_descriptions = {
                    'percent': '百分比体系',
                    'count': '计数体系 (1000进制)',
                    'data_bits': '数据-比特体系 (1000进制)',
                    'data_bytes': '数据-字节体系 (1024进制)',
                    'data_rate_bits': '数据速率-比特体系 (1000进制)',
                    'datarate_bytes': '数据速率-字节体系 (1024进制)',
                    'time': '时间体系',
                    'hertz': '频率体系 (1000进制)',
                    'standalone': '独立单位（不支持转换）',
                }

                result = []
                for system, units in grouped_units.items():
                    result.append({
                        'system_name': system,
                        'system_description': system_descriptions.get(system, system),
                        'units': units,
                    })

                serializer = UnitSystemSerializer(result, many=True)
                return WebUtils.response_success(serializer.data)

        except Exception as e:
            logger.error(f"按体系获取单位失败: {e}")
            return WebUtils.response_error(f"按体系获取单位失败: {str(e)}")

    @extend_schema(
        summary="单位转换",
        description="将数值从源单位转换到目标单位（必须是同一体系）",
        request=UnitConversionRequestSerializer,
        responses={200: UnitConversionResponseSerializer},
    )
    @action(methods=['POST'], detail=False, url_path='convert')
    def convert_units(self, request):
        """单位转换"""
        try:
            request_serializer = UnitConversionRequestSerializer(data=request.data)
            if not request_serializer.is_valid():
                return WebUtils.response_error("请求参数错误", data=request_serializer.errors)

            values = request_serializer.validated_data['values']
            source_unit = request_serializer.validated_data['source_unit']
            target_unit = request_serializer.validated_data['target_unit']

            # 检查是否可以转换
            if not UnitConverter.is_convertible(source_unit, target_unit):
                return WebUtils.response_error(
                    f"单位 '{source_unit}' 和 '{target_unit}' 不属于同一体系，无法转换"
                )

            # 执行转换
            converted_values = UnitConverter.convert_values(values, source_unit, target_unit)

            # 获取展示单位
            source_display = UnitConverter.get_display_unit(source_unit)
            target_display = UnitConverter.get_display_unit(target_unit)

            response_data = {
                'converted_values': converted_values,
                'source_unit': source_unit,
                'target_unit': target_unit,
                'source_display': source_display,
                'target_display': target_display,
            }

            response_serializer = UnitConversionResponseSerializer(response_data)
            return WebUtils.response_success(response_serializer.data)

        except Exception as e:
            logger.error(f"单位转换失败: {e}")
            return WebUtils.response_error(f"单位转换失败: {str(e)}")

    @extend_schema(
        summary="单位建议",
        description="根据数值范围自动建议合适的单位并进行转换",
        request=UnitSuggestionRequestSerializer,
        responses={200: UnitSuggestionResponseSerializer},
    )
    @action(methods=['POST'], detail=False, url_path='suggest')
    def suggest_unit(self, request):
        """单位建议"""
        try:
            request_serializer = UnitSuggestionRequestSerializer(data=request.data)
            if not request_serializer.is_valid():
                return WebUtils.response_error("请求参数错误", data=request_serializer.errors)

            values = request_serializer.validated_data['values']
            source_unit = request_serializer.validated_data['source_unit']
            strategy = request_serializer.validated_data.get('strategy', 'median')

            # 自动转换
            converted_values, suggested_unit = UnitConverter.auto_convert(
                values, source_unit, strategy=strategy
            )

            # 获取展示单位
            suggested_display = UnitConverter.get_display_unit(suggested_unit)

            response_data = {
                'suggested_unit': suggested_unit,
                'suggested_display': suggested_display,
                'converted_values': converted_values,
            }

            response_serializer = UnitSuggestionResponseSerializer(response_data)
            return WebUtils.response_success(response_serializer.data)

        except Exception as e:
            logger.error(f"单位建议失败: {e}")
            return WebUtils.response_error(f"单位建议失败: {str(e)}")

    @extend_schema(
        summary="检查单位可转换性",
        description="检查两个单位是否可以互相转换",
        parameters=[
            OpenApiParameter(
                name='source_unit',
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="源单位"
            ),
            OpenApiParameter(
                name='target_unit',
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="目标单位"
            ),
        ],
    )
    @action(methods=['GET'], detail=False, url_path='check-convertible')
    def check_convertible(self, request):
        """检查单位可转换性"""
        try:
            source_unit = request.query_params.get('source_unit')
            target_unit = request.query_params.get('target_unit')

            if not source_unit or not target_unit:
                return WebUtils.response_error("缺少 source_unit 或 target_unit 参数")

            is_convertible = UnitConverter.is_convertible(source_unit, target_unit)

            return WebUtils.response_success({
                'source_unit': source_unit,
                'target_unit': target_unit,
                'is_convertible': is_convertible,
            })

        except Exception as e:
            logger.error(f"检查单位可转换性失败: {e}")
            return WebUtils.response_error(f"检查单位可转换性失败: {str(e)}")
