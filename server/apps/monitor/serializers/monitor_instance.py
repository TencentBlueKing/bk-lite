from rest_framework import serializers

from apps.monitor.models.monitor_object import MonitorInstance


class MonitorInstanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorInstance
        fields = '__all__'