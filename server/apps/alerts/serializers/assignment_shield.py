# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.alert_operator import AlertAssignment, AlertShield


class AlertAssignmentModelSerializer(serializers.ModelSerializer):
    """
    Serializer for AlertAssignment model.
    This serializer is used to assign alerts to users or teams.
    """

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
