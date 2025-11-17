# -- coding: utf-8 --
# @File: directory_serializers.py
# @Time: 2025/7/18 10:59
# @Author: windyzhao
from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer
from apps.operation_analysis.serializers.base_serializers import BaseFormatTimeSerializer
from apps.operation_analysis.models.models import Dashboard, Directory, Topology, Architecture


class DirectoryModelSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "directory"

    class Meta:
        model = Directory
        fields = "__all__"
        extra_kwargs = {
        }


class DashboardModelSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "directory.dashboard"

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


class TopologyModelSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "directory.topology"

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


class ArchitectureModelSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "directory.architecture"

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
