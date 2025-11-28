from rest_framework import serializers

from apps.console_mgmt.models import UserAppSet


class UserAppSetSerializer(serializers.ModelSerializer):
    """用户应用配置集序列化器"""

    class Meta:
        model = UserAppSet
        fields = ["id", "username", "domain", "app_config_list"]
        read_only_fields = ["id"]
