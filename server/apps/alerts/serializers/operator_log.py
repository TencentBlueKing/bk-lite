# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.operator_log import OperatorLog


class OperatorLogModelSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = OperatorLog
        fields = "__all__"
