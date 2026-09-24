"""脚本序列化器"""

from rest_framework import serializers

from apps.core.utils.serializers import TeamSerializer
from apps.job_mgmt.models import Script
from apps.job_mgmt.services.param_crypto import ParamCrypto
from apps.job_mgmt.services.script_normalize import normalize_script_line_endings
from apps.job_mgmt.utils.i18n import serializer_message


def validate_script_name_unique_in_organizations(name, team, exclude_script_id=None):
    """校验同名脚本的组织集合互不重叠。"""
    requested_teams = {str(team_id) for team_id in team}
    same_name_scripts = Script.objects.filter(name=name)
    if exclude_script_id is not None:
        same_name_scripts = same_name_scripts.exclude(pk=exclude_script_id)

    existing_teams = same_name_scripts.values_list("team", flat=True).iterator()
    has_conflict = any(requested_teams.intersection(str(team_id) for team_id in (script_teams or [])) for script_teams in existing_teams)
    if has_conflict:
        raise serializers.ValidationError({"name": "同一组织内已存在同名脚本"})


class ScriptListSerializer(TeamSerializer):
    """脚本列表序列化器（返回精简字段）"""

    script_type_display = serializers.CharField(source="get_script_type_display", read_only=True)

    class Meta:
        model = Script
        fields = [
            "id",
            "name",
            "description",
            "script_type",
            "script_type_display",
            "timeout",
            "team_name",
            "is_built_in",
            "updated_at",
        ]


class ScriptSerializer(serializers.ModelSerializer):
    """脚本序列化器"""

    script_type_display = serializers.CharField(source="get_script_type_display", read_only=True)

    class Meta:
        model = Script
        fields = [
            "id",
            "name",
            "description",
            "script_type",
            "script_type_display",
            "content",
            "params",
            "timeout",
            "team",
            "is_built_in",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_by", "updated_at"]

    def to_representation(self, instance):
        """返回前端时隐藏加密参数的默认值"""
        data = super().to_representation(instance)
        if data.get("params"):
            data["params"] = ParamCrypto.mask_encrypted_defaults(data["params"])
        return data


class ScriptCreateSerializer(serializers.ModelSerializer):
    """脚本创建序列化器"""

    class Meta:
        model = Script
        fields = [
            "name",
            "description",
            "script_type",
            "content",
            "params",
            "timeout",
            "team",
            "is_built_in",
        ]

    def validate_content(self, value):
        """验证脚本内容不能为空,并按 script_type 规范化换行符"""
        if not value or not value.strip():
            raise serializers.ValidationError(serializer_message(self, "error.script_content_empty", "Script content cannot be empty"))
        script_type = self.initial_data.get("script_type", "") or ""
        return normalize_script_line_endings(value, script_type)

    def validate_params(self, value):
        """加密参数定义中的默认值"""
        if value:
            ParamCrypto.encrypt_param_defaults(value)
        return value

    def validate_team(self, value):
        """验证组织不能为空"""
        if not value:
            raise serializers.ValidationError(serializer_message(self, "error.organization_required", "Organization is required"))
        return value


class ScriptUpdateSerializer(serializers.ModelSerializer):
    """脚本更新序列化器"""

    class Meta:
        model = Script
        fields = [
            "name",
            "description",
            "script_type",
            "content",
            "params",
            "timeout",
            "team",
            "is_built_in",
        ]

    def validate_content(self, value):
        """验证脚本内容不能为空,并按当前 script_type 规范化换行符"""
        if value is not None and not value.strip():
            raise serializers.ValidationError(serializer_message(self, "error.script_content_empty", "Script content cannot be empty"))
        if value is None:
            return value
        # update 场景下若用户未传 script_type,从已有 instance 读取,避免误规范化
        script_type = self.initial_data.get("script_type")
        if not script_type and self.instance is not None:
            script_type = self.instance.script_type or ""
        return normalize_script_line_endings(value, script_type or "")

    def validate_params(self, value):
        """加密默认值；脱敏占位符沿用 instance 中原密文，避免二次保存把掩码写进库。"""
        if value:
            existing = self.instance.params if self.instance is not None else None
            ParamCrypto.prepare_param_defaults_for_save(value, existing_params=existing)
        return value

    def validate_team(self, value):
        """验证组织不能为空"""
        if not value:
            raise serializers.ValidationError(serializer_message(self, "error.organization_required", "Organization is required"))
        return value


class ScriptBatchDeleteSerializer(serializers.Serializer):
    """脚本批量删除序列化器"""

    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="要删除的脚本ID列表")


class ScriptExportSerializer(serializers.Serializer):
    """脚本批量导出序列化器"""

    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="要导出的脚本ID列表")


class ScriptImportSerializer(serializers.Serializer):
    """脚本批量导入序列化器"""

    file = serializers.FileField(help_text="脚本库 ZIP 文件")
    team = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="目标组织ID列表")

    def validate_file(self, value):
        name = (getattr(value, "name", "") or "").lower()
        if not name.endswith(".zip"):
            raise serializers.ValidationError(serializer_message(self, "error.zip_only", "Only .zip files are supported"))
        return value

    def validate_team(self, value):
        if not value:
            raise serializers.ValidationError(serializer_message(self, "error.organization_required", "Organization is required"))
        return value
