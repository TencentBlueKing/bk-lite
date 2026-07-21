# -- coding: utf-8 --
# @File: datasource_serializers.py
# @Time: 2025/11/3 16:05
# @Author: windyzhao
from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer
from apps.operation_analysis.constants.import_export import SENSITIVE_PLACEHOLDER, is_sensitive_field_name
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace
from apps.operation_analysis.serializers.base_serializers import BaseFormatTimeSerializer


def redact_sensitive_config(value):
    if isinstance(value, list):
        return [redact_sensitive_config(item) for item in value]
    if not isinstance(value, dict):
        return value

    redacted = {}
    for key, item in value.items():
        if is_sensitive_field_name(key):
            redacted[key] = SENSITIVE_PLACEHOLDER if item not in (None, "") else item
        else:
            redacted[key] = redact_sensitive_config(item)
    return redacted


def merge_redacted_config(existing, incoming):
    if isinstance(incoming, list):
        existing_items = existing if isinstance(existing, list) else []
        return [
            merge_redacted_config(existing_items[index] if index < len(existing_items) else None, item)
            for index, item in enumerate(incoming)
        ]
    if not isinstance(incoming, dict):
        return incoming

    existing_items = existing if isinstance(existing, dict) else {}
    merged = {}
    for key, item in incoming.items():
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
        fields = "__all__"
        extra_kwargs = {}

    def validate_source_type(self, value):
        allowed = {choice[0] for choice in DataSourceAPIModel.SOURCE_TYPE_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError("source_type 不支持")
        return value

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
            key = field.get("key", "")
            if not key or not key.strip():
                raise serializers.ValidationError(f"[{idx}].key 不能为空")
            if key in keys:
                raise serializers.ValidationError(f"[{idx}].key '{key}' 重复")
            keys.append(key)

        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["connection_config"] = redact_sensitive_config(data.get("connection_config"))
        data["query_config"] = redact_sensitive_config(data.get("query_config"))
        return data


class DataSourceBriefSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "datasource"
    tag = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = DataSourceAPIModel
        # 包含 params / field_schema,确保 widgetSelector 选中后能直接拿到完整配置,
        # 不用再回查 detail endpoint 也能渲染"展示列"和"搜索字段"。
        # connection_config / query_config 仍不返(可能含敏感信息)。
        fields = [
            "id", "name", "rest_api", "source_type", "desc",
            "chart_type", "tag", "groups",
            "params", "field_schema",
        ]


class DataSourceDetailSerializer(DataSourceAPIModelSerializer):
    namespaces = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    tag = serializers.PrimaryKeyRelatedField(many=True, read_only=True)


class NameSpaceModelSerializer(BaseFormatTimeSerializer):
    class Meta:
        model = NameSpace
        fields = "__all__"
        extra_kwargs = {
            "password": {"write_only": True},
        }
