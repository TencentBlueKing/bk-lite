"""分发文件序列化器"""

from rest_framework import serializers

from apps.job_mgmt.models import DistributionFile


class DistributionFileSerializer(serializers.ModelSerializer):
    """分发文件序列化器"""

    class Meta:
        model = DistributionFile
        fields = ["id", "original_name", "file_key", "created_at"]
        read_only_fields = fields


class DistributionFileUploadSerializer(serializers.Serializer):
    """分发文件上传序列化器"""

    file = serializers.FileField(help_text="上传的文件")

    def validate_file(self, value):
        """验证文件大小"""
        max_size = 500 * 1024 * 1024  # 500MB
        if value.size > max_size:
            raise serializers.ValidationError(f"文件 {value.name} 超过 500MB 限制")
        return value
