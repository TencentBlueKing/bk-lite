# -- coding: utf-8 --
# @File: datasource_serializers.py
# @Time: 2025/11/3 16:05
# @Author: windyzhao
from apps.core.utils.serializers import AuthSerializer
from apps.operation_analysis.serializers.base_serializers import BaseFormatTimeSerializer
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace, DataSourceTag


class DataSourceAPIModelSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "datasource"

    class Meta:
        model = DataSourceAPIModel
        fields = "__all__"
        extra_kwargs = {
        }


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
