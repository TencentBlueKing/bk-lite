from rest_framework import serializers

from apps.monitor.models.monitor_policy import MonitorAlert, MonitorAlertMetricSnapshot


class MonitorAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorAlert
        fields = "__all__"
        # 告警中心补偿状态机的内部簿记字段，仅由服务端维护，禁止客户端写入
        read_only_fields = ["alert_center_notified", "alert_center_retry_count"]


class MonitorAlertUpdateSerializer(MonitorAlertSerializer):
    """用户只允许修改告警状态，归属、身份和生命周期簿记均由服务端维护。"""

    allowed_input_fields = {"status", "update_baseline"}

    class Meta(MonitorAlertSerializer.Meta):
        read_only_fields = [field.name for field in MonitorAlert._meta.fields if field.name != "status"]

    def validate(self, attrs):
        forbidden_fields = set(self.initial_data) - self.allowed_input_fields
        if forbidden_fields:
            raise serializers.ValidationError({field: "该字段不允许修改" for field in sorted(forbidden_fields)})
        return super().validate(attrs)


class MonitorAlertMetricSnapshotSerializer(serializers.ModelSerializer):
    """告警指标快照序列化器"""

    class Meta:
        model = MonitorAlertMetricSnapshot
        fields = "__all__"
