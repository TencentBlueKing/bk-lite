"""
单位相关的序列化器
"""

from rest_framework import serializers


class UnitSerializer(serializers.Serializer):
    """单位序列化器"""

    unit_id = serializers.CharField(help_text="单位ID")
    unit_name = serializers.CharField(help_text="单位名称（用于展示）")
    system = serializers.CharField(allow_null=True, help_text="所属单位体系")
    display_unit = serializers.CharField(help_text="展示格式")
    description = serializers.CharField(help_text="单位描述")
    is_standalone = serializers.BooleanField(help_text="是否为独立单位（不支持转换）")


class UnitSystemSerializer(serializers.Serializer):
    """单位体系序列化器"""

    system_name = serializers.CharField(help_text="体系名称")
    system_description = serializers.CharField(help_text="体系描述")
    units = UnitSerializer(many=True, help_text="该体系下的所有单位")


class UnitConversionRequestSerializer(serializers.Serializer):
    """单位转换请求序列化器"""

    values = serializers.ListField(
        child=serializers.FloatField(allow_null=True),
        help_text="待转换的数值列表"
    )
    source_unit = serializers.CharField(help_text="源单位")
    target_unit = serializers.CharField(help_text="目标单位")


class UnitConversionResponseSerializer(serializers.Serializer):
    """单位转换响应序列化器"""

    converted_values = serializers.ListField(
        child=serializers.FloatField(allow_null=True),
        help_text="转换后的数值列表"
    )
    source_unit = serializers.CharField(help_text="源单位")
    target_unit = serializers.CharField(help_text="目标单位")
    source_display = serializers.CharField(help_text="源单位展示格式")
    target_display = serializers.CharField(help_text="目标单位展示格式")


class UnitSuggestionRequestSerializer(serializers.Serializer):
    """单位建议请求序列化器"""

    values = serializers.ListField(
        child=serializers.FloatField(allow_null=True),
        help_text="数值列表"
    )
    source_unit = serializers.CharField(help_text="源单位")
    strategy = serializers.ChoiceField(
        choices=['median', 'max', 'mean', 'p95'],
        default='median',
        help_text="选择策略：median（中位数）、max（最大值）、mean（平均值）、p95（95分位数）"
    )


class UnitSuggestionResponseSerializer(serializers.Serializer):
    """单位建议响应序列化器"""

    suggested_unit = serializers.CharField(help_text="建议的单位ID")
    suggested_display = serializers.CharField(help_text="建议的单位展示格式")
    converted_values = serializers.ListField(
        child=serializers.FloatField(allow_null=True),
        help_text="转换后的数值列表"
    )
