# -- coding: utf-8 --
from copy import deepcopy

from rest_framework import serializers

from apps.alerts.common.source_adapter.constants import DEFAULT_SOURCE_CONFIG, build_prometheus_source_config, build_zabbix_source_config
from apps.alerts.constants.constants import AlertsSourceTypes
from apps.alerts.models.alert_source import AlertSource

INTEGRATION_SECRET_PLACEHOLDER = "{{TEAM_SECRET}}"
PUBLIC_CONFIG_KEYS = {
    "url",
    "method",
    "content_type",
    "timeout",
    "params",
    "headers",
    "examples",
    "event_fields_mapping",
    "event_fields_desc_mapping",
    "description",
}
SENSITIVE_CONFIG_KEY_PARTS = {
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "secret_key",
    "token",
}


def _is_sensitive_config_key(key):
    normalized = str(key).strip().lower().replace("-", "_")
    return any(part == normalized or part in normalized for part in SENSITIVE_CONFIG_KEY_PARTS)


def _sanitize_config_value(value, credentials):
    if isinstance(value, dict):
        return {key: _sanitize_config_value(item, credentials) for key, item in value.items() if not _is_sensitive_config_key(key)}
    if isinstance(value, list):
        return [_sanitize_config_value(item, credentials) for item in value]
    if isinstance(value, str):
        sanitized = value
        for credential in credentials:
            if isinstance(credential, str) and credential:
                sanitized = sanitized.replace(credential, INTEGRATION_SECRET_PLACEHOLDER)
        return sanitized
    return value


def build_public_alert_source_config(source):
    """Build the allowlisted, credential-free config projection returned by detail queries."""
    config = source.config if isinstance(source.config, dict) else {}
    credentials = [
        source.secret,
        *(source.team_secrets or {}).values(),
        "your_source_secret",
        "{{SECRET}}",
    ]
    projected = {key: config[key] for key in PUBLIC_CONFIG_KEYS if key in config}
    return _sanitize_config_value(projected, credentials)


class AlertSourceModelSerializer(serializers.ModelSerializer):
    """
    Serializer for AlertSource model.
    """

    event_count = serializers.SerializerMethodField()
    last_event_time = serializers.SerializerMethodField()
    config = serializers.JSONField(write_only=True, required=False)

    class Meta:
        model = AlertSource
        fields = [
            "id",
            "event_count",
            "last_event_time",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "name",
            "source_id",
            "source_type",
            "config",
            "logo",
            "access_type",
            "is_active",
            "is_effective",
            "description",
        ]

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
        from django.utils import timezone

        return timezone.localtime(last_event.received_at).strftime(format_time)


class AlertSourceOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertSource
        fields = ["id", "name", "source_id", "source_type"]


class AlertSourceOverviewSerializer(serializers.ModelSerializer):
    event_count = serializers.SerializerMethodField()
    last_event_time = serializers.SerializerMethodField()

    class Meta:
        model = AlertSource
        fields = [
            "id",
            "name",
            "source_id",
            "source_type",
            "logo",
            "access_type",
            "is_active",
            "is_effective",
            "description",
            "event_count",
            "last_event_time",
        ]

    get_event_count = staticmethod(AlertSourceModelSerializer.get_event_count)
    get_last_event_time = staticmethod(AlertSourceModelSerializer.get_last_event_time)


class AlertSourceDetailSerializer(AlertSourceOverviewSerializer):
    config = serializers.SerializerMethodField()

    class Meta(AlertSourceOverviewSerializer.Meta):
        fields = AlertSourceOverviewSerializer.Meta.fields + [
            "config",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]

    @staticmethod
    def get_config(obj):
        return build_public_alert_source_config(obj)


class TeamSecretRequestSerializer(serializers.Serializer):
    team_id = serializers.IntegerField(min_value=1)


class K8sRenderRequestSerializer(TeamSecretRequestSerializer):
    server_url = serializers.CharField(required=False, allow_blank=True, default="")
    cluster_name = serializers.CharField(required=False, allow_blank=True, default="")
    push_source_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    insecure_skip_verify = serializers.BooleanField(required=False, default=False)
