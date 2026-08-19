"""作业管理统一 OpenAPI 网关请求契约。"""

from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer
from apps.job_mgmt.constants import OverwriteStrategy


class FileDistributeTargetSerializer(OpenAPIRequestSerializer):
    """文件分发目标引用；执行端只信任这里声明并校验过的标识。"""

    target_id = serializers.IntegerField(required=False, min_value=1)
    node_id = serializers.CharField(required=False, max_length=100)
    name = serializers.CharField(required=False, max_length=128)
    ip = serializers.IPAddressField(required=False)
    os = serializers.CharField(required=False, max_length=32)


class FileDistributeRequestSerializer(OpenAPIRequestSerializer):
    """可信身份文件分发请求；团队身份只允许由网关注入。"""

    name = serializers.CharField(max_length=256)
    file_keys = serializers.ListField(
        child=serializers.CharField(max_length=512),
        min_length=1,
        max_length=100,
    )
    target_source = serializers.ChoiceField(choices=["node_mgmt", "manual"])
    target_list = serializers.ListField(
        child=FileDistributeTargetSerializer(),
        min_length=1,
        max_length=500,
    )
    target_path = serializers.CharField(max_length=512)
    overwrite_strategy = serializers.ChoiceField(
        choices=[choice[0] for choice in OverwriteStrategy.CHOICES],
        required=False,
        default=OverwriteStrategy.OVERWRITE,
    )
    timeout = serializers.IntegerField(required=False, default=600, min_value=1, max_value=86400)

    def validate(self, attrs):
        id_field = "target_id" if attrs["target_source"] == "manual" else "node_id"
        unexpected_id_field = "node_id" if id_field == "target_id" else "target_id"
        errors = {}
        for index, target in enumerate(attrs["target_list"]):
            if id_field not in target:
                errors[index] = {id_field: ["required"]}
            elif unexpected_id_field in target:
                errors[index] = {unexpected_id_field: ["not allowed for target_source"]}
        if errors:
            raise serializers.ValidationError({"target_list": errors})
        return attrs
