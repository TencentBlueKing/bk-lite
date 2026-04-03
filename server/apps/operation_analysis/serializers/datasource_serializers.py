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
