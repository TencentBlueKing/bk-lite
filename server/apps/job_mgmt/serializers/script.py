"""脚本序列化器"""

from rest_framework import serializers

from apps.job_mgmt.models import Script
from apps.job_mgmt.services.param_crypto import ParamCrypto


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
        """验证脚本内容不能为空"""
        if not value or not value.strip():
            raise serializers.ValidationError("脚本内容不能为空")
        return value

    def validate_params(self, value):
        """加密参数定义中的默认值"""
        if value:
            ParamCrypto.encrypt_param_defaults(value)
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
        """验证脚本内容不能为空"""
        if value is not None and not value.strip():
            raise serializers.ValidationError("脚本内容不能为空")
        return value

    def validate_params(self, value):
        """加密参数定义中的默认值"""
        if value:
            ParamCrypto.encrypt_param_defaults(value)
        return value


class ScriptBatchDeleteSerializer(serializers.Serializer):
    """脚本批量删除序列化器"""

    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="要删除的脚本ID列表")
