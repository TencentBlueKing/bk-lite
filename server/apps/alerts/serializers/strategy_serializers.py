from rest_framework import serializers
from apps.alerts.models import AlarmStrategy


class AlarmStrategySerializer(serializers.ModelSerializer):
    """聚合规则序列化器"""
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = AlarmStrategy
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {}
