# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.models import Event


class EventModelSerializer(serializers.ModelSerializer):
    """
    Serializer for Event model.
    """

    # 格式化时间字段
    start_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    end_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    source_name = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = '__all__'
        extra_kwargs = {
            # "events": {"write_only": True},  # events 字段只读
            "start_time": {"read_only": True},
            "end_time": {"read_only": True},
            "labels": {"write_only": True},
            # "raw_data": {"write_only": True},
        }

    @staticmethod
    def get_source_name(obj):
        """
        Get the names of the sources associated with the alert.
        通过 Alert -> Events -> AlertSource 获取告警源名称
        """
        # 如果使用了注解（推荐）
        return obj.source.name
