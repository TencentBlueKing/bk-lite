from rest_framework import serializers

from apps.cmdb.models.config_file_version import ConfigFileVersion


class ConfigFileVersionSerializer(serializers.ModelSerializer):
    content_key = serializers.SerializerMethodField()

    @staticmethod
    def get_content_key(obj):
        return obj.content_key

    class Meta:
        model = ConfigFileVersion
        fields = [
            "id",
            "collect_task_id",
            "instance_id",
            "instance_uuid",
            "model_id",
            "version",
            "file_path",
            "file_name",
            "content_hash",
            "content_key",
            "file_size",
            "status",
            "error_message",
            "created_at",
        ]


class ConfigFileListSerializer(serializers.Serializer):
    latest_version_id = serializers.IntegerField()
    file_path = serializers.CharField()
    file_name = serializers.CharField()
    collect_task_id = serializers.IntegerField()
    latest_version = serializers.CharField()
    latest_status = serializers.CharField()
    latest_created_at = serializers.DateTimeField()
