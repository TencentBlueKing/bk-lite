# -- coding: utf-8 --
# @File: serializers.py
# @Time: 2025/7/18 10:59
# @Author: windyzhao
from rest_framework import serializers
from apps.operation_analysis.models import DataSourceAPIModel, Dashboard, Directory, Topology, NameSpace, DataSourceTag, Architecture


class BaseFormatTimeSerializer(serializers.ModelSerializer):
    # 格式化时间字段
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)


class DataSourceAPIModelSerializer(BaseFormatTimeSerializer):
    class Meta:
        model = DataSourceAPIModel
        fields = "__all__"
        extra_kwargs = {
        }


class DirectoryModelSerializer(BaseFormatTimeSerializer):
    class Meta:
        model = Directory
        fields = "__all__"
        extra_kwargs = {
        }


class DashboardModelSerializer(BaseFormatTimeSerializer):
    class Meta:
        model = Dashboard
        fields = "__all__"
        extra_kwargs = {
        }

    def create(self, validated_data):
        """
        验证创建的时候 有没有带directory_id 如果没有则报错
        """
        if 'directory' not in validated_data:
            raise serializers.ValidationError({"directory": ["directory is required for creation."]})
        return super().create(validated_data)


class TopologyModelSerializer(BaseFormatTimeSerializer):
    class Meta:
        model = Topology
        fields = "__all__"
        extra_kwargs = {}

    def create(self, validated_data):
        """
        验证创建的时候 有没有带directory_id 如果没有则报错
        """
        if 'directory' not in validated_data:
            raise serializers.ValidationError({"directory": ["directory is required for creation."]})
        return super().create(validated_data)


class ArchitectureModelSerializer(BaseFormatTimeSerializer):
    class Meta:
        model = Architecture
        fields = "__all__"
        extra_kwargs = {}

    def create(self, validated_data):
        """
        验证创建的时候 有没有带directory_id 如果没有则报错
        """
        if 'directory' not in validated_data:
            raise serializers.ValidationError({"directory": ["directory is required for creation."]})
        return super().create(validated_data)


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
