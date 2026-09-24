"""分发文件序列化器"""

from rest_framework import serializers

from apps.job_mgmt.models import DistributionFile
from apps.job_mgmt.utils.i18n import serializer_message


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
            raise serializers.ValidationError(
                serializer_message(self, "error.file_size_exceeds_500mb", "File {name} exceeds the 500MB limit", name=value.name)
            )
        return value
