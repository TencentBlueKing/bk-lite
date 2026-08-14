from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer
from apps.operation_analysis.models.datasource_models import DataConnection, DataSourceAPIModel
from apps.operation_analysis.serializers.base_serializers import BaseFormatTimeSerializer
from apps.operation_analysis.services.data_connection.config_crypto import (
    encrypt_connection_config,
    merge_connection_config,
    redact_connection_config,
)
from apps.operation_analysis.services.data_connection.groups import find_groups_outside_connection, is_groups_subset, normalize_group_ids

CONTROLLED_REST_HEADERS = {
    "connection",
    "content-length",
    "host",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def validate_rest_headers(headers):
    if headers is None:
        return {}
    if not isinstance(headers, dict):
        raise serializers.ValidationError("headers 必须为对象")
    controlled = sorted(str(name) for name in headers if str(name).strip().lower() in CONTROLLED_REST_HEADERS)
    if controlled:
        raise serializers.ValidationError(f"不允许设置受控 Header: {', '.join(controlled)}")
    return headers


def _summarize_endpoint(connection_type, config):
    config = config if isinstance(config, dict) else {}
    if connection_type in {DataConnection.TYPE_MYSQL, DataConnection.TYPE_POSTGRESQL}:
        host = config.get("host") or ""
        port = config.get("port") or ""
        database = config.get("database") or ""
        if host and port:
            return f"{host}:{port}/{database}".rstrip("/")
        return host or database or ""
    if connection_type == DataConnection.TYPE_REST_API:
        return config.get("base_url") or config.get("url") or ""
    return ""


def _validate_connection_config_shape(connection_type, config):
    if not isinstance(config, dict):
        raise serializers.ValidationError("config 必须为对象")
    if connection_type in {DataConnection.TYPE_MYSQL, DataConnection.TYPE_POSTGRESQL}:
        required = ("host", "port", "database", "username", "password")
        missing = [key for key in required if config.get(key) in (None, "")]
        if missing:
            raise serializers.ValidationError(f"缺少连接字段: {', '.join(missing)}")
    elif connection_type == DataConnection.TYPE_REST_API:
        if not (config.get("base_url") or config.get("url")):
            raise serializers.ValidationError("REST 连接必须提供 base_url")
        config["headers"] = validate_rest_headers(config.get("headers"))
    else:
        raise serializers.ValidationError("connection_type 不支持")
    return config


class DataConnectionSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "datasource"
    reference_count = serializers.IntegerField(read_only=True)
    endpoint_summary = serializers.SerializerMethodField()

    class Meta:
        model = DataConnection
        fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "groups",
            "name",
            "connection_type",
            "description",
            "is_active",
            "config",
            "reference_count",
            "endpoint_summary",
        ]
        extra_kwargs = {
            "connection_type": {"required": True},
        }

    def get_endpoint_summary(self, instance):
        return _summarize_endpoint(instance.connection_type, redact_connection_config(instance.config or {}))

    def validate_connection_type(self, value):
        allowed = {choice[0] for choice in DataConnection.TYPE_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError("connection_type 不支持")
        if self.instance and self.instance.connection_type != value:
            raise serializers.ValidationError("连接类型创建后不可修改")
        return value

    def validate_config(self, value):
        if value in (None, ""):
            value = {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("config 必须为对象")
        if self.instance:
            value = merge_connection_config(self.instance.config or {}, value)
        return value

    def validate_groups(self, value):
        groups = normalize_group_ids(value)
        if not groups:
            raise serializers.ValidationError("groups 不能为空")
        if self.instance:
            conflicting = []
            for datasource in self.instance.data_sources.all().only("id", "name", "groups"):
                outside = find_groups_outside_connection(datasource.groups, groups)
                if outside:
                    conflicting.append({"id": datasource.id, "name": datasource.name, "outside_groups": outside})
            if conflicting:
                raise serializers.ValidationError(
                    {
                        "message": "缩小授权组织会导致引用数据源越界",
                        "conflicts": conflicting,
                    }
                )
        return groups

    def validate(self, attrs):
        attrs = super().validate(attrs)
        connection_type = attrs.get("connection_type", getattr(self.instance, "connection_type", None))
        config = attrs.get("config", getattr(self.instance, "config", {}) if self.instance else {})
        attrs["config"] = _validate_connection_config_shape(connection_type, config)
        return attrs

    def create(self, validated_data):
        validated_data["config"] = encrypt_connection_config(validated_data.get("config") or {})
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "config" in validated_data:
            validated_data["config"] = encrypt_connection_config(validated_data["config"] or {})
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["config"] = redact_connection_config(instance.config or {})
        if "reference_count" not in data or data["reference_count"] is None:
            data["reference_count"] = getattr(instance, "reference_count", None)
            if data["reference_count"] is None:
                data["reference_count"] = instance.data_sources.count()
        return data


class DataConnectionTestSerializer(serializers.Serializer):
    connection_type = serializers.ChoiceField(choices=DataConnection.TYPE_CHOICES)
    config = serializers.DictField()

    def validate(self, attrs):
        attrs["config"] = _validate_connection_config_shape(
            attrs["connection_type"],
            dict(attrs["config"]),
        )
        return attrs


class DataConnectionReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSourceAPIModel
        fields = ["id", "name", "source_type", "groups"]


def validate_datasource_connection_binding(attrs, instance=None):
    connection = attrs.get("connection", serializers.empty)
    if connection is serializers.empty:
        connection = getattr(instance, "connection", None) if instance else None

    source_type = attrs.get("source_type", getattr(instance, "source_type", None) if instance else None)
    groups = attrs.get("groups", getattr(instance, "groups", None) if instance else None)
    overrides = attrs.get(
        "connection_overrides",
        getattr(instance, "connection_overrides", {}) if instance else {},
    )
    if overrides in (None, ""):
        overrides = {}
    if not isinstance(overrides, dict):
        raise serializers.ValidationError({"connection_overrides": "必须为对象"})

    if connection is None:
        attrs["connection_overrides"] = overrides or {}
        return attrs

    if source_type not in {
        DataSourceAPIModel.SOURCE_TYPE_MYSQL,
        DataSourceAPIModel.SOURCE_TYPE_POSTGRESQL,
        DataSourceAPIModel.SOURCE_TYPE_REST_API,
    }:
        raise serializers.ValidationError({"connection": "仅 MySQL/PostgreSQL/REST 可引用数据连接"})

    if connection.connection_type != source_type:
        raise serializers.ValidationError({"connection": "数据连接类型必须与数据源类型一致"})

    if not is_groups_subset(groups, connection.groups):
        outside = find_groups_outside_connection(groups, connection.groups)
        raise serializers.ValidationError({"groups": f"数据源组织必须是连接授权组织的子集，越界组织: {outside}"})

    if source_type in {DataSourceAPIModel.SOURCE_TYPE_MYSQL, DataSourceAPIModel.SOURCE_TYPE_POSTGRESQL}:
        allowed = {"database"}
    else:
        allowed = {"path", "method", "timeout"}
    unexpected = sorted(set(overrides.keys()) - allowed)
    if unexpected:
        raise serializers.ValidationError({"connection_overrides": f"不允许覆盖字段: {', '.join(unexpected)}"})

    if source_type == DataSourceAPIModel.SOURCE_TYPE_REST_API:
        path = overrides.get("path")
        if path not in (None, "") and (str(path).startswith("http://") or str(path).startswith("https://") or str(path).startswith("//")):
            raise serializers.ValidationError({"connection_overrides": "path 必须为相对路径"})

    attrs["connection_overrides"] = overrides
    # 引用连接时禁止在 connection_config 中保留主机/凭据。
    connection_config = attrs.get("connection_config")
    if connection_config is None and instance is not None:
        connection_config = instance.connection_config or {}
    if connection_config is None:
        connection_config = {}
    if source_type in {DataSourceAPIModel.SOURCE_TYPE_MYSQL, DataSourceAPIModel.SOURCE_TYPE_POSTGRESQL}:
        attrs["connection_config"] = {}
    else:
        # REST：请求方法/超时可保留在 connection_config，path 走 overrides；禁止 url/headers。
        cleaned = {key: value for key, value in (connection_config or {}).items() if key in {"method", "timeout", "path"}}
        if "path" in cleaned and "path" not in overrides:
            overrides = {**overrides, "path": cleaned.pop("path")}
            attrs["connection_overrides"] = overrides
        attrs["connection_config"] = cleaned
    return attrs
