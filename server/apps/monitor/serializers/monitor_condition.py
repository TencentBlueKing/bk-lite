from rest_framework import serializers

from apps.monitor.models.monitor_condition import MonitorCondition


class MonitorConditionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorCondition
        fields = "__all__"
