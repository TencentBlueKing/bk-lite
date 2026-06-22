# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.alert_operator import AlertAssignment, AlertShield


class AlertAssignmentModelSerializer(serializers.ModelSerializer):
    """
    Serializer for AlertAssignment model.
    This serializer is used to assign alerts to users or teams.
    """

    def validate_config(self, value):
        """校验升级链配置块（未启用则跳过）。"""
        from apps.alerts.service.escalation_service import EscalationService

        block = (value or {}).get("escalation")
        if not block or not block.get("enabled"):
            return value
        if EscalationService.parse_escalation_config(value) is None:
            raise serializers.ValidationError(
                "升级链配置无效：模式须为 append/替换，至少一层，每层须有处理人且等待时长大于 0"
            )
        return value

    class Meta:
        model = AlertAssignment
        fields = "__all__"
        extra_kwargs = {
            # 'alert_id': {'read_only': True},
            # 'status': {'required': True},
            # 'operator': {'required': True},
        }


class AlertShieldModelSerializer(serializers.ModelSerializer):
    """
    Serializer for AlertAssignment model.
    This serializer is used to assign alerts to users or teams.
    """

    class Meta:
        model = AlertShield
        fields = "__all__"
        extra_kwargs = {}
