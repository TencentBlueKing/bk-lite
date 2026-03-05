"""高危路径序列化器"""

from rest_framework import serializers

from apps.job_mgmt.models import DangerousPath


class DangerousPathSerializer(serializers.ModelSerializer):
    """高危路径序列化器"""

    class Meta:
        model = DangerousPath
        fields = [
            "id",
            "name",
            "description",
            "pattern",
            "level",
            "is_enabled",
            "team",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_by", "updated_at"]


class DangerousPathCreateSerializer(serializers.ModelSerializer):
    """高危路径创建序列化器"""

    class Meta:
        model = DangerousPath
        fields = [
            "name",
            "description",
            "pattern",
            "level",
            "is_enabled",
            "team",
        ]


class DangerousPathUpdateSerializer(serializers.ModelSerializer):
    """高危路径更新序列化器"""

    name = serializers.CharField(required=False)
    pattern = serializers.CharField(required=False)

    class Meta:
        model = DangerousPath
        fields = [
            "name",
            "description",
            "pattern",
            "level",
            "is_enabled",
            "team",
        ]
