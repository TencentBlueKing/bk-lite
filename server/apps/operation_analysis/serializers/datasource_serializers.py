# -- coding: utf-8 --
# @File: datasource_serializers.py
# @Time: 2025/11/3 16:05
# @Author: windyzhao
from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer
from apps.operation_analysis.serializers.base_serializers import BaseFormatTimeSerializer
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace, DataSourceTag


class DataSourceAPIModelSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "datasource"

    class Meta:
        model = DataSourceAPIModel
        fields = "__all__"
        extra_kwargs = {}

    def validate_response_field_schema_config(self, value):
        if not value:
            return value

        if not isinstance(value, dict):
            raise serializers.ValidationError("response_field_schema_config 必须为对象")

        fields = value.get("fields", [])
        if not fields:
            return value

        keys = []
        for idx, field in enumerate(fields):
            key = field.get("key", "")
            if not key or not key.strip():
                raise serializers.ValidationError(f"fields[{idx}].key 不能为空")
            if key in keys:
                raise serializers.ValidationError(f"fields[{idx}].key '{key}' 重复")
            keys.append(key)

        return value


class NameSpaceModelSerializer(BaseFormatTimeSerializer):
    class Meta:
        model = NameSpace
        fields = "__all__"
        extra_kwargs = {
            "password": {"write_only": True},
        }


class DataSourceTagModelSerializer(BaseFormatTimeSerializer):
    class Meta:
        model = DataSourceTag
        fields = "__all__"
