from rest_framework import serializers

from apps.monitor.models.monitor_policy import MonitorAlert, MonitorAlertMetricSnapshot


class MonitorAlertSerializer(serializers.ModelSerializer):

    class Meta:
        model = MonitorAlert
        fields = '__all__'


class MonitorAlertMetricSnapshotSerializer(serializers.ModelSerializer):
    """告警指标快照序列化器"""

    class Meta:
        model = MonitorAlertMetricSnapshot
        fields = '__all__'
