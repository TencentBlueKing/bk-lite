"""危险规则序列化器"""

from rest_framework import serializers

from apps.job_mgmt.models import DangerousRule


class DangerousRuleSerializer(serializers.ModelSerializer):
    """危险规则序列化器"""

    class Meta:
        model = DangerousRule
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


class DangerousRuleCreateSerializer(serializers.ModelSerializer):
    """危险规则创建序列化器"""

    class Meta:
        model = DangerousRule
        fields = [
            "name",
            "description",
            "pattern",
            "level",
            "is_enabled",
            "team",
        ]


class DangerousRuleUpdateSerializer(serializers.ModelSerializer):
    """危险规则更新序列化器"""

    name = serializers.CharField(required=False)
    pattern = serializers.CharField(required=False)

    class Meta:
        model = DangerousRule
        fields = [
            "name",
            "description",
            "pattern",
            "level",
            "is_enabled",
            "team",
        ]
