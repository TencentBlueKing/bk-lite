# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.alert_source import AlertSource


class AlertSourceModelSerializer(serializers.ModelSerializer):
    """
    Serializer for AlertSource model.
    """
    event_count = serializers.SerializerMethodField()
    last_event_time = serializers.SerializerMethodField()

    class Meta:
        model = AlertSource
        fields = "__all__"
        extra_kwargs = {
            # "secret": {"write_only": True},
            # "config": {"write_only": True},
            "last_active_time": {"write_only": True},
            "is_delete": {"write_only": True},
        }

    @staticmethod
    def get_event_count(obj):
        return obj.event_set.count()

    @staticmethod
    def get_last_event_time(obj):
        """
        获取最近一次事件时间
        """
        format_time = "%Y-%m-%d %H:%M:%S"
        last_event = obj.event_set.order_by('-received_at').first()
        if not last_event or not last_event.received_at:
            return ""
        # 如果需要格式化时间，可以在这里进行
        return last_event.received_at.strftime(format_time)
