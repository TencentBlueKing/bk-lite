from rest_framework import serializers
from apps.cmdb.models import UserPersonalConfig


class UserPersonalConfigSerializer(serializers.ModelSerializer):
    """用户个人配置序列化器"""

    class Meta:
        model = UserPersonalConfig
        fields = ["id", "config_key", "config_value", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
