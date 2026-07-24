"""补丁库序列化器"""

import re

from rest_framework import serializers

from apps.core.utils.serializers import TeamSerializer
from apps.patch_mgmt.models import LinuxPatchDetail, Patch, WindowsPatchDetail


class WindowsPatchDetailSerializer(serializers.ModelSerializer):
    """Windows 补丁详情序列化器（支持读写）"""

    class Meta:
        model = WindowsPatchDetail
        fields = ["kb_number", "product_list", "architectures", "ms_bulletin"]


class LinuxPatchDetailSerializer(serializers.ModelSerializer):
    """Linux 补丁详情序列化器（支持读写）"""

    class Meta:
        model = LinuxPatchDetail
        fields = ["pkg_name", "pkg_version", "distro_name", "os_version_range", "architectures", "repo_type"]


class PatchListSerializer(TeamSerializer):
    """补丁列表序列化器

    列表即返回 windows_detail/linux_detail（KB/产品/架构、包版本/系统版本/repo 类型等），
    使补丁库表格无需逐行再查详情即可展示这些字段；viewset 已 select_related 避免 N+1。
    同时支持在 create/update 时传入 windows_detail/linux_detail 一并保存。
    """

    os_type_display = serializers.CharField(source="get_os_type_display", read_only=True)
    patch_type_display = serializers.CharField(source="get_patch_type_display", read_only=True)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    pkg_status_display = serializers.CharField(source="get_pkg_status_display", read_only=True)
    windows_detail = WindowsPatchDetailSerializer(required=False, allow_null=True)
    linux_detail = LinuxPatchDetailSerializer(required=False, allow_null=True)
    sources = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    source_type = serializers.SerializerMethodField()
    baseline_requirement_count = serializers.SerializerMethodField()
    package_info = serializers.SerializerMethodField()

    class Meta:
        model = Patch
        fields = [
            "id",
            "title",
            "os_type",
            "os_type_display",
            "patch_type",
            "patch_type_display",
            "severity",
            "severity_display",
            "pkg_status",
            "pkg_status_display",
            "cve_list",
            "applicable_scope",
            "sources",
            "source_type",
            "package_info",
            "windows_detail",
            "linux_detail",
            "released_at",
            "last_synced_at",
            "team",
            "team_name",
            "created_by",
            "created_at",
            "updated_at",
            "baseline_requirement_count",
        ]
        read_only_fields = ["id", "last_synced_at", "created_by", "created_at", "updated_at"]

    def get_source_type(self, obj):
        first_source = obj.sources.first()
        return first_source.source_type if first_source else None

    def get_baseline_requirement_count(self, obj):
        return obj.baseline_requirements.count()

    def get_package_info(self, obj):
        if obj.os_type != "windows":
            return None
        try:
            detail = obj.windows_detail
        except WindowsPatchDetail.DoesNotExist:
            return None
        if not detail.package_original_name:
            return None
        return {
            "file_name": detail.package_original_name,
            "file_size": detail.package_size,
            "sha256": detail.package_sha256,
            "extension": detail.package_extension,
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        os_type = attrs.get("os_type", getattr(self.instance, "os_type", None))
        windows_detail = attrs.get("windows_detail")
        if os_type != "windows" or windows_detail is None:
            return attrs

        raw_kb = str(windows_detail.get("kb_number") or "").strip()
        match = re.fullmatch(r"(?i:KB)(\d+)", raw_kb)
        if not match:
            raise serializers.ValidationError(
                {"windows_detail": {"kb_number": "KB 编号必须为 KB 加数字"}}
            )

        kb_number = f"KB{match.group(1)}"
        duplicate = WindowsPatchDetail.objects.filter(kb_number__iexact=kb_number)
        if self.instance:
            duplicate = duplicate.exclude(patch=self.instance)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"windows_detail": {"kb_number": f"{kb_number} 已存在，不允许重复创建"}}
            )
        windows_detail["kb_number"] = kb_number
        return attrs

    def create(self, validated_data):
        windows_detail_data = validated_data.pop("windows_detail", None)
        linux_detail_data = validated_data.pop("linux_detail", None)
        patch = super().create(validated_data)
        self._save_detail(patch, windows_detail_data, linux_detail_data)
        return patch

    def update(self, instance, validated_data):
        windows_detail_data = validated_data.pop("windows_detail", None)
        linux_detail_data = validated_data.pop("linux_detail", None)
        patch = super().update(instance, validated_data)
        self._save_detail(patch, windows_detail_data, linux_detail_data)
        return patch

    def _save_detail(self, patch, windows_detail_data, linux_detail_data):
        if patch.os_type == "windows" and windows_detail_data:
            WindowsPatchDetail.objects.update_or_create(
                patch=patch, defaults=windows_detail_data
            )
        if patch.os_type == "linux" and linux_detail_data:
            LinuxPatchDetail.objects.update_or_create(
                patch=patch, defaults=linux_detail_data
            )


class PatchDetailSerializer(PatchListSerializer):
    """补丁详情序列化器"""

    class Meta(PatchListSerializer.Meta):
        fields = PatchListSerializer.Meta.fields + [
            "applicable_rules",
            "dependency_ids",
            "replacement_ids",
            "updated_by",
            "updated_at",
        ]
