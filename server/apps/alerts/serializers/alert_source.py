# -- coding: utf-8 --
from copy import deepcopy

from rest_framework import serializers

from apps.alerts.common.source_adapter.constants import (
    DEFAULT_SOURCE_CONFIG,
    build_prometheus_source_config,
    build_zabbix_source_config,
)
from apps.alerts.constants.constants import AlertsSourceTypes
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
            # "config": {"write_only": True},
            "last_active_time": {"write_only": True},
            "is_delete": {"write_only": True},
            "secret": {"write_only": True},
            "team_secrets": {"write_only": True},
        }

    @staticmethod
    def _deep_merge_config(base, override):
        merged = deepcopy(base)
        for key, value in (override or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = AlertSourceModelSerializer._deep_merge_config(merged[key], value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _build_default_config(source_type, source_id):
        if source_type == AlertsSourceTypes.PROMETHEUS:
            return build_prometheus_source_config(source_id)
        if source_type == AlertsSourceTypes.ZABBIX:
            return build_zabbix_source_config(source_id)
        return deepcopy(DEFAULT_SOURCE_CONFIG)

    def validate(self, attrs):
        source_type = attrs.get("source_type", getattr(self.instance, "source_type", None))
        source_id = attrs.get("source_id", getattr(self.instance, "source_id", ""))
        incoming_config = attrs.get("config")

        if source_type and source_id:
            default_config = self._build_default_config(source_type, source_id)
            attrs["config"] = self._deep_merge_config(default_config, incoming_config or {})

        return attrs

    @staticmethod
    def get_event_count(obj):
        return obj.event_set.count()

    @staticmethod
    def get_last_event_time(obj):
        """
        获取最近一次事件时间
        """
        format_time = "%Y-%m-%d %H:%M:%S"
        last_event = obj.event_set.order_by("-received_at").first()
        if not last_event or not last_event.received_at:
            return ""
        # 如果需要格式化时间，可以在这里进行
        return last_event.received_at.strftime(format_time)
