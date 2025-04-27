from rest_framework import serializers

from apps.monitor.models.monitor_policy import MonitorPolicy


class MonitorPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorPolicy
        fields = '__all__'
