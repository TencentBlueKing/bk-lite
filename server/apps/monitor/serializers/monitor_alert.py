from rest_framework import serializers

from apps.monitor.models.monitor_policy import MonitorAlert, MonitorAlertMetricSnapshot


class MonitorAlertSerializer(serializers.ModelSerializer):

    class Meta:
        model = MonitorAlert
        fields = '__all__'
        # 告警中心补偿状态机的内部簿记字段，仅由服务端维护，禁止客户端写入
        read_only_fields = ['alert_center_notified', 'alert_center_retry_count']


class MonitorAlertMetricSnapshotSerializer(serializers.ModelSerializer):
    """告警指标快照序列化器"""

    class Meta:
        model = MonitorAlertMetricSnapshot
        fields = '__all__'
