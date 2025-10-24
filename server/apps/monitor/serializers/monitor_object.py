from rest_framework import serializers

from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectOrganizationRule, MonitorObjectType


class MonitorObjectTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorObjectType
        fields = '__all__'


class MonitorObjectSerializer(serializers.ModelSerializer):
    type_info = MonitorObjectTypeSerializer(source='type', read_only=True)
    
    class Meta:
        model = MonitorObject
        fields = '__all__'


class MonitorObjectOrganizationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorObjectOrganizationRule
        fields = '__all__'
