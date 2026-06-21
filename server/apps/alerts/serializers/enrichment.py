# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.enrichment import EnrichmentRule


class EnrichmentRuleModelSerializer(serializers.ModelSerializer):
    """告警丰富规则序列化器。"""

    def validate_input_binding(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("入参绑定必须是对象 {provider_param: event_field}")
        return value

    def validate_output_projection(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("出参投影必须是列表 [{source, as}]")
        for item in value:
            if not isinstance(item, dict) or "source" not in item:
                raise serializers.ValidationError("每项投影须含 source 字段")
        return value

    class Meta:
        model = EnrichmentRule
        fields = "__all__"
        extra_kwargs = {}
