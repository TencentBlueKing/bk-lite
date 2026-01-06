"""
单位管理相关视图
"""

from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.utils.web_utils import WebUtils
from apps.monitor.serializers.unit import UnitSerializer, UnitSystemSerializer
from apps.monitor.utils.unit_converter import UnitConverter
from apps.core.logger import monitor_logger as logger


class UnitViewSet(viewsets.ViewSet):
    """
    单位管理视图集

    提供单位列表查询功能，用于前端配置指标时选择单位
    """

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

    @action(methods=['GET'], detail=False, url_path='by_system')
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

