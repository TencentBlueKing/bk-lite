"""Playbook序列化器"""

from rest_framework import serializers

from apps.job_mgmt.models import Playbook


class PlaybookSerializer(serializers.ModelSerializer):
    """Playbook序列化器"""

    class Meta:
        model = Playbook
        fields = [
            "id",
            "name",
            "description",
            "file_name",
            "file_key",
            "bucket_name",
            "file_size",
            "entry_file",
            "params",
            "timeout",
            "team",
            "is_preset",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_by", "updated_at"]


class PlaybookCreateSerializer(serializers.ModelSerializer):
    """Playbook创建序列化器"""

    class Meta:
        model = Playbook
        fields = [
            "name",
            "description",
            "file_name",
            "file_key",
            "bucket_name",
            "file_size",
            "entry_file",
            "params",
            "timeout",
            "team",
            "is_preset",
        ]

    def validate_file_key(self, value):
        """验证文件Key不能为空"""
        if not value or not value.strip():
            raise serializers.ValidationError("文件Key不能为空")
        return value

    def validate_file_name(self, value):
        """验证文件名不能为空"""
        if not value or not value.strip():
            raise serializers.ValidationError("文件名不能为空")
        return value


class PlaybookUpdateSerializer(serializers.ModelSerializer):
    """Playbook更新序列化器"""

    class Meta:
        model = Playbook
        fields = [
            "name",
            "description",
            "file_name",
            "file_key",
            "bucket_name",
            "file_size",
            "entry_file",
            "params",
            "timeout",
            "team",
            "is_preset",
        ]


class PlaybookBatchDeleteSerializer(serializers.Serializer):
    """Playbook批量删除序列化器"""

    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, help_text="要删除的PlaybookID列表")
