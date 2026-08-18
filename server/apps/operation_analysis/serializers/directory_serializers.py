# -- coding: utf-8 --
# @File: directory_serializers.py
# @Time: 2025/7/18 10:59
# @Author: windyzhao
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from apps.core.utils.serializers import AuthSerializer
from apps.operation_analysis.constants.canvas_refresh import CANVAS_REFRESH_INTERVAL_MS
from apps.operation_analysis.constants.import_export import ObjectType
from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, Report, Screen, Topology
from apps.operation_analysis.serializers.base_serializers import BaseFormatTimeSerializer
from apps.operation_analysis.services.import_export.view_sets import normalize_canvas_view_sets_for_storage
from apps.operation_analysis.services.report_view_sets import normalize_report_view_sets

CANVAS_REFRESH_INTERVAL_KWARGS = {"required": False, "default": serializers.empty}
REPORT_VERSION_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


class ReportVersionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "report_version_conflict"
    default_detail = "报表已被其他人更新，请刷新后重试"


def with_canvas_refresh_interval_kwargs(extra_kwargs: dict) -> dict:
    return {**extra_kwargs, "refresh_interval": CANVAS_REFRESH_INTERVAL_KWARGS}


class DirectoryModelSerializer(BaseFormatTimeSerializer, AuthSerializer):
    permission_key = "directory"

    @staticmethod
    def _validate_parent_candidate(instance_pk, parent):
        candidate = Directory(pk=instance_pk, parent=parent)
        try:
            candidate.clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error

    def validate_parent(self, parent):
        self._validate_parent_candidate(getattr(self.instance, "pk", None), parent)
        return parent

    def update(self, instance, validated_data):
        if "parent" not in validated_data:
            return super().update(instance, validated_data)

        parent_id = getattr(validated_data["parent"], "pk", None)
        with transaction.atomic():
            list(Directory.objects.select_for_update().order_by("pk").values_list("pk", flat=True))
            locked_instance = Directory.objects.get(pk=instance.pk)
            validated_data["parent"] = Directory.objects.get(pk=parent_id) if parent_id is not None else None
            self._validate_parent_candidate(locked_instance.pk, validated_data["parent"])
            return super().update(locked_instance, validated_data)

    class Meta:
        model = Directory
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
            "parent",
            "is_active",
            "desc",
            "is_build_in",
            "build_in_key",
            "permissions",
        ]
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
        try:
            directory_chain = [directory, *directory.get_parent_chain()]
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error

        for current in directory_chain:
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


class CanvasRefreshIntervalSerializerMixin:
    def validate_refresh_interval(self, value):
        if value not in CANVAS_REFRESH_INTERVAL_MS:
            raise serializers.ValidationError("refresh_interval 必须是 0、60000、300000 或 600000")
        return value


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


class DashboardModelSerializer(CanvasRefreshIntervalSerializerMixin, CanvasObjectSerializer):
    permission_key = "directory.dashboard"

    class Meta(CanvasObjectSerializer.Meta):
        model = Dashboard
        extra_kwargs = with_canvas_refresh_interval_kwargs(CanvasObjectSerializer.Meta.extra_kwargs)


class TopologyModelSerializer(CanvasRefreshIntervalSerializerMixin, CanvasObjectSerializer):
    permission_key = "directory.topology"

    class Meta(CanvasObjectSerializer.Meta):
        model = Topology
        extra_kwargs = with_canvas_refresh_interval_kwargs(CanvasObjectSerializer.Meta.extra_kwargs)


class ArchitectureModelSerializer(CanvasObjectSerializer):
    permission_key = "directory.architecture"

    class Meta(CanvasObjectSerializer.Meta):
        model = Architecture


class ScreenModelSerializer(CanvasRefreshIntervalSerializerMixin, CanvasObjectSerializer):
    permission_key = "directory.screen"

    class Meta(CanvasObjectSerializer.Meta):
        model = Screen
        extra_kwargs = with_canvas_refresh_interval_kwargs(CanvasObjectSerializer.Meta.extra_kwargs)

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


class ReportModelSerializer(CanvasRefreshIntervalSerializerMixin, CanvasObjectSerializer):
    permission_key = "directory.report"
    # updated_at 同时作为报表乐观锁令牌；必须保留数据库微秒精度，不能使用全局秒级展示格式。
    updated_at = serializers.DateTimeField(read_only=True, format=REPORT_VERSION_DATETIME_FORMAT)
    expected_updated_at = serializers.DateTimeField(write_only=True, required=False)

    class Meta(CanvasObjectSerializer.Meta):
        model = Report
        extra_kwargs = with_canvas_refresh_interval_kwargs(CanvasObjectSerializer.Meta.extra_kwargs)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None and "view_sets" not in attrs:
            attrs["view_sets"] = normalize_report_view_sets({})
        if "view_sets" in attrs:
            try:
                attrs["view_sets"] = normalize_report_view_sets(attrs["view_sets"])
            except ValueError as error:
                raise serializers.ValidationError({"view_sets": [str(error)]}) from error

            if self.instance is not None and "expected_updated_at" not in attrs:
                raise serializers.ValidationError({"expected_updated_at": ["保存报表内容时必须提供当前版本"]})
        return attrs

    def create(self, validated_data):
        validated_data.pop("expected_updated_at", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        expected_updated_at = validated_data.pop("expected_updated_at", None)
        if "view_sets" not in validated_data:
            return super().update(instance, validated_data)

        with transaction.atomic():
            locked_report = Report.objects.select_for_update().get(pk=instance.pk)
            if expected_updated_at != locked_report.updated_at:
                raise ReportVersionConflict()
            return super().update(locked_report, validated_data)
