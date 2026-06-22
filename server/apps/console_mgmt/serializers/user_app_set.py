from rest_framework import serializers

from apps.console_mgmt.models import UserAppSet


class AppConfigItemSerializer(serializers.Serializer):
    """单条应用配置项的结构校验器"""

    name = serializers.CharField(max_length=255)
    is_build_in = serializers.BooleanField(default=False)
    visible = serializers.BooleanField(default=True)
    order = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=255),
        required=False,
        default=list,
    )
    url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    logo = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class UserAppSetSerializer(serializers.ModelSerializer):
    """用户应用配置集序列化器"""

    app_config_list = AppConfigItemSerializer(many=True)

    class Meta:
        model = UserAppSet
        fields = ["id", "username", "domain", "app_config_list"]
        read_only_fields = ["id"]
