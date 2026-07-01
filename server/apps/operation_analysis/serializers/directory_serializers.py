# -- coding: utf-8 --
# @File: directory_serializers.py
# @Time: 2025/7/18 10:59
# @Author: windyzhao
from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer
from apps.operation_analysis.constants.import_export import ObjectType
from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, Report, Screen, Topology
from apps.operation_analysis.serializers.base_serializers import BaseFormatTimeSerializer
from apps.operation_analysis.services.import_export.view_sets import normalize_canvas_view_sets_for_storage


class DirectoryModelSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "directory"

    class Meta:
        model = Directory
        fields = "__all__"
        extra_kwargs = {
            "is_build_in": {"read_only": True},
            "build_in_key": {"read_only": True},
        }


class DirectoryChainVisibilityMixin:
    def validate(self, attrs):
        attrs = super().validate(attrs)
        self._validate_directory_chain_visibility(attrs)
        return attrs

    def _validate_directory_chain_visibility(self, attrs):
        directory = attrs.get("directory", getattr(self.instance, "directory", None))
        groups = attrs.get("groups", getattr(self.instance, "groups", [])) or []

        if directory is None or not groups:
            return

        target_groups = {int(group_id) for group_id in groups if group_id is not None}
        conflicts = []
        current = directory

        while current is not None:
            directory_groups = {int(group_id) for group_id in (current.groups or []) if group_id is not None}
            missing_groups = sorted(target_groups - directory_groups)
            if missing_groups:
                conflicts.append(
                    {
                        "directory": {
                            "id": current.id,
                            "name": current.name,
                            "parent_id": current.parent_id,
                        },
                        "missing_groups": missing_groups,
                    }
                )
            current = current.parent

        if conflicts:
            raise serializers.ValidationError(
                {
                    "detail": "所选组织超出目录可见范围，请调整目录或对象的组织范围",
                    "data": {"conflicts": conflicts},
                }
            )


class BuiltinPermissionMixin:
    """内置对象权限处理：内置对象只返回 View 权限"""

    def get_permissions(self, instance):
        if getattr(instance, "is_build_in", False):
            return ["View"]
        return super().get_permissions(instance)


class CanvasObjectSerializer(DirectoryChainVisibilityMixin, BuiltinPermissionMixin, BaseFormatTimeSerializer, AuthSerializer):
    class Meta:
        fields = "__all__"
        extra_kwargs = {
            "is_build_in": {"read_only": True},
            "build_in_key": {"read_only": True},
        }

    def create(self, validated_data):
        """
        验证创建的时候 有没有带directory_id 如果没有则报错
        """
        if "directory" not in validated_data:
            raise serializers.ValidationError({"directory": ["directory is required for creation."]})
        return super().create(validated_data)


class DashboardModelSerializer(CanvasObjectSerializer):
    permission_key = "directory.dashboard"

    class Meta(CanvasObjectSerializer.Meta):
        model = Dashboard


class TopologyModelSerializer(CanvasObjectSerializer):
    permission_key = "directory.topology"

    class Meta(CanvasObjectSerializer.Meta):
        model = Topology


class ArchitectureModelSerializer(CanvasObjectSerializer):
    permission_key = "directory.architecture"

    class Meta(CanvasObjectSerializer.Meta):
        model = Architecture


class ScreenModelSerializer(CanvasObjectSerializer):
    permission_key = "directory.screen"

    class Meta(CanvasObjectSerializer.Meta):
        model = Screen

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None and "view_sets" not in attrs:
            raise serializers.ValidationError({"view_sets": ["view_sets is required for screen."]})

        if "view_sets" in attrs:
            try:
                attrs["view_sets"] = normalize_canvas_view_sets_for_storage(
                    attrs["view_sets"],
                    ObjectType.SCREEN,
                )
            except ValueError as error:
                raise serializers.ValidationError({"view_sets": [str(error)]}) from error

        return attrs


class ReportModelSerializer(CanvasObjectSerializer):
    permission_key = "directory.report"

    class Meta(CanvasObjectSerializer.Meta):
        model = Report
