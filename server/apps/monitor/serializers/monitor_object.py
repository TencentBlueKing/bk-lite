from rest_framework import serializers

from apps.monitor.models.monitor_object import MonitorObject, MonitorInstanceGroupingRule


class MonitorObjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorObject
        fields = '__all__'


class MonitorInstanceGroupingRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorInstanceGroupingRule
        fields = '__all__'
