"""
单位相关的序列化器
"""

from rest_framework import serializers


class UnitSerializer(serializers.Serializer):
    """单位序列化器"""

    unit_id = serializers.CharField(help_text="单位ID")
    unit_name = serializers.CharField(help_text="单位名称（配置指标管理时展示）")
    system = serializers.CharField(allow_null=True, help_text="所属单位体系")
    display_unit = serializers.CharField(help_text="展示格式（监控视图、监控策略、告警通知中显示数据时用）")
    description = serializers.CharField(help_text="单位描述")
    is_standalone = serializers.BooleanField(help_text="是否为独立单位（不支持转换）")


class UnitSystemSerializer(serializers.Serializer):
    """单位体系序列化器"""

    system_name = serializers.CharField(help_text="体系名称")
    system_description = serializers.CharField(help_text="体系描述")
    units = UnitSerializer(many=True, help_text="该体系下的所有单位")
