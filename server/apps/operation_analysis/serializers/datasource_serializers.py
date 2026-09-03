# -- coding: utf-8 --
# @File: datasource_serializers.py
# @Time: 2025/11/3 16:05
# @Author: windyzhao
from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.operation_analysis.common.datasource_security import LEGACY_RAW_MONITOR_QUERY_ERROR, is_legacy_raw_monitor_query
from apps.operation_analysis.constants.import_export import SENSITIVE_PLACEHOLDER, is_sensitive_field_name
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace
from apps.operation_analysis.serializers.base_serializers import BaseFormatTimeSerializer
from apps.operation_analysis.serializers.data_connection_serializers import validate_datasource_connection_binding, validate_rest_headers

TRANSFORM_ALLOWED_SOURCE_TYPES = {
    DataSourceAPIModel.SOURCE_TYPE_REST_API,
    DataSourceAPIModel.SOURCE_TYPE_EXCEL,
}
DISABLED_TRANSFORM_CONFIG = {"enabled": False, "language": "python", "script": ""}


def transform_config_for_source_type(source_type, transform_config):
    if source_type not in TRANSFORM_ALLOWED_SOURCE_TYPES:
        return dict(DISABLED_TRANSFORM_CONFIG)
    if isinstance(transform_config, dict):
        return transform_config
    return {}


def redact_sensitive_config(value):
    if isinstance(value, list):
        return [redact_sensitive_config(item) for item in value]
    if not isinstance(value, dict):
        return value

    redacted = {}
    for key, item in value.items():
        # Spec: REST Header names are visible; every Header value is sensitive.
        if key == "headers" and isinstance(item, dict):
            redacted[key] = {
                header_key: (SENSITIVE_PLACEHOLDER if header_value not in (None, "") else header_value) for header_key, header_value in item.items()
            }
            continue
        if is_sensitive_field_name(key):
            redacted[key] = SENSITIVE_PLACEHOLDER if item not in (None, "") else item
        else:
            redacted[key] = redact_sensitive_config(item)
    return redacted


def merge_redacted_config(existing, incoming):
    if isinstance(incoming, list):
        existing_items = existing if isinstance(existing, list) else []
        return [merge_redacted_config(existing_items[index] if index < len(existing_items) else None, item) for index, item in enumerate(incoming)]
    if not isinstance(incoming, dict):
        return incoming

    existing_items = existing if isinstance(existing, dict) else {}
    merged = {}
    for key, item in incoming.items():
        if key == "headers" and isinstance(item, dict):
            existing_headers = existing_items.get(key) if isinstance(existing_items.get(key), dict) else {}
            merged_headers = {}
            for header_key, header_value in item.items():
                if header_value == SENSITIVE_PLACEHOLDER:
                    merged_headers[header_key] = existing_headers.get(header_key)
                else:
                    merged_headers[header_key] = header_value
            merged[key] = merged_headers
            continue
        if item == SENSITIVE_PLACEHOLDER and is_sensitive_field_name(key):
            merged[key] = existing_items.get(key)
        else:
            merged[key] = merge_redacted_config(existing_items.get(key), item)
    return merged


class DataSourceTagModelSerializer(BaseFormatTimeSerializer):
    class Meta:
        model = DataSourceTag
        fields = "__all__"


class DataSourceAPIModelSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "datasource"

    class Meta:
        model = DataSourceAPIModel
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
            "rest_api",
            "desc",
            "source_type",
            "connection",
            "connection_config",
            "connection_overrides",
            "query_config",
            "transform_config",
            "is_active",
            "params",
            "chart_type",
            "field_schema",
            "is_build_in",
            "build_in_key",
            "namespaces",
            "tag",
        ]
        extra_kwargs = {
            "is_build_in": {"read_only": True},
            "build_in_key": {"read_only": True},
            "connection": {"required": False, "allow_null": True},
            "connection_overrides": {"required": False},
            "groups": {"required": True},
        }

    def validate_source_type(self, value):
        allowed = {choice[0] for choice in DataSourceAPIModel.SOURCE_TYPE_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError("source_type 不支持")
        return value

    def validate_groups(self, value):
        groups = value or []
        if self.instance is not None and getattr(self.instance, "is_build_in", False):
            return groups
        if not groups:
            raise serializers.ValidationError("必须选择所属组织")
        return groups

    def validate_connection_config(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("connection_config 必须为对象")
        if self.instance:
            return merge_redacted_config(self.instance.connection_config or {}, value)
        return value

    def validate_query_config(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("query_config 必须为对象")
        if self.instance:
            return merge_redacted_config(self.instance.query_config or {}, value)
        return value

    def validate_field_schema(self, value):
        if not value:
            return value

        if not isinstance(value, list):
            raise serializers.ValidationError("field_schema 必须为数组")

        keys = []
        for idx, field in enumerate(value):
            if not isinstance(field, dict):
                raise serializers.ValidationError(f"[{idx}] 必须为对象")
            key = field.get("key", "")
            if not isinstance(key, str) or not key.strip():
                raise serializers.ValidationError(f"[{idx}].key 不能为空")
            if key in keys:
                raise serializers.ValidationError(f"[{idx}].key '{key}' 重复")
            keys.append(key)

        return value

    def validate_params(self, value):
        if not value:
            return value
        if not isinstance(value, list):
            raise serializers.ValidationError("params 必须为数组")

        bindable_types = {"string", "timeRange", "dateRange"}
        for index, param in enumerate(value):
            if not isinstance(param, dict):
                raise serializers.ValidationError(f"[{index}] 必须为对象")
            if param.get("filterType") == "filter" and param.get("type") not in bindable_types:
                raise serializers.ValidationError(f"[{index}].type 仅 string、timeRange、dateRange 支持筛选联动")
        return value

    def validate_transform_config(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("transform_config 必须为对象")
        source_type = None
        initial_data = getattr(self, "initial_data", None)
        if isinstance(initial_data, dict):
            source_type = initial_data.get("source_type")
        if not source_type and self.instance:
            source_type = self.instance.source_type
        if source_type not in TRANSFORM_ALLOWED_SOURCE_TYPES:
            return dict(DISABLED_TRANSFORM_CONFIG)
        enabled = bool(value.get("enabled"))
        language = (value.get("language") or "python").lower()
        script = value.get("script") or ""
        if enabled and language != "python":
            raise serializers.ValidationError("仅支持 language=python")
        if enabled and (not isinstance(script, str) or not script.strip()):
            raise serializers.ValidationError("启用转换时 script 不能为空")
        return {
            "enabled": enabled,
            "language": "python",
            "script": script if isinstance(script, str) else "",
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        attrs = validate_datasource_connection_binding(attrs, self.instance)
        source_type = attrs.get(
            "source_type",
            getattr(self.instance, "source_type", DataSourceAPIModel.SOURCE_TYPE_NATS),
        )
        rest_api = attrs.get("rest_api", getattr(self.instance, "rest_api", ""))
        if is_legacy_raw_monitor_query(source_type=source_type, rest_api=rest_api):
            raise serializers.ValidationError({"rest_api": LEGACY_RAW_MONITOR_QUERY_ERROR})

        transform_config = attrs.get(
            "transform_config",
            getattr(self.instance, "transform_config", {}) if self.instance else {},
        )
        # 编辑切类型时前端可能漏传 transform_config，不能沿用旧 REST/Excel 的 enabled 配置。
        attrs["transform_config"] = transform_config_for_source_type(source_type, transform_config)

        should_validate_headers = self.instance is None or "connection_config" in attrs or "source_type" in attrs
        if source_type == DataSourceAPIModel.SOURCE_TYPE_REST_API and should_validate_headers:
            connection_config = attrs.get(
                "connection_config",
                getattr(self.instance, "connection_config", {}) if self.instance else {},
            )
            if isinstance(connection_config, dict) and "headers" in connection_config:
                validate_rest_headers(connection_config.get("headers"))

        should_validate_target = self.instance is None or "connection_config" in attrs or "source_type" in attrs
        if source_type != DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS or not should_validate_target:
            return attrs

        connection_config = attrs.get(
            "connection_config",
            getattr(self.instance, "connection_config", {}) or {},
        )
        url = connection_config.get("url", "") if isinstance(connection_config, dict) else ""
        try:
            SSRFValidator.validate(url)
        except SSRFError as exc:
            detail = serializers.ErrorDetail(str(exc), code=exc.code)
            raise serializers.ValidationError({"connection_config": {"url": [detail]}}) from exc

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["connection_config"] = redact_sensitive_config(data.get("connection_config"))
        data["query_config"] = redact_sensitive_config(data.get("query_config"))
        data["connection_id"] = instance.connection_id
        if instance.source_type == DataSourceAPIModel.SOURCE_TYPE_EXCEL:
            from apps.operation_analysis.services.excel_materialize import build_excel_materialization_payload

            data["excel_materialization"] = build_excel_materialization_payload(instance)
        return data

    def update(self, instance, validated_data):
        previous_type = instance.source_type
        previous_transform = instance.transform_config if isinstance(instance.transform_config, dict) else {}
        updated = super().update(instance, validated_data)
        left_excel = previous_type == DataSourceAPIModel.SOURCE_TYPE_EXCEL and updated.source_type != DataSourceAPIModel.SOURCE_TYPE_EXCEL
        if left_excel:
            from apps.operation_analysis.services.excel_materialize import abandon_excel_materialization

            abandon_excel_materialization(updated)
            updated.refresh_from_db()
            return updated
        if updated.source_type != DataSourceAPIModel.SOURCE_TYPE_EXCEL:
            return updated

        new_transform = updated.transform_config if isinstance(updated.transform_config, dict) else {}
        transform_changed = bool(previous_transform.get("enabled")) != bool(new_transform.get("enabled")) or (
            previous_transform.get("script") or ""
        ) != (new_transform.get("script") or "")
        if not transform_changed:
            return updated

        has_source = bool(
            (updated.excel_success_slot and updated.excel_success_slot.source_file)
            or (updated.excel_candidate_slot and updated.excel_candidate_slot.source_file)
        )
        if not has_source:
            return updated

        from apps.operation_analysis.services.excel_materialize.submit import schedule_resubmit_excel_from_saved_source

        schedule_resubmit_excel_from_saved_source(updated.id)
        return updated


class DataSourceBriefSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "datasource"
    tag = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = DataSourceAPIModel
        # 包含 params / field_schema,确保 widgetSelector 选中后能直接拿到完整配置,
        # 不用再回查 detail endpoint 也能渲染"展示列"和"搜索字段"。
        # connection_config / query_config 仍不返(可能含敏感信息)。
        fields = [
            "id",
            "name",
            "rest_api",
            "source_type",
            "desc",
            "chart_type",
            "tag",
            "groups",
            "params",
            "field_schema",
            "is_build_in",
            "connection",
        ]


class DataSourceDetailSerializer(DataSourceAPIModelSerializer):
    namespaces = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    tag = serializers.PrimaryKeyRelatedField(many=True, read_only=True)


class NameSpaceModelSerializer(BaseFormatTimeSerializer):
    def update(self, instance, validated_data):
        password = validated_data.pop("password", serializers.empty)
        if password is not serializers.empty:
            instance.set_password(password)
        return super().update(instance, validated_data)

    class Meta:
        model = NameSpace
        fields = "__all__"
        extra_kwargs = {
            "password": {"write_only": True, "allow_blank": True},
        }
