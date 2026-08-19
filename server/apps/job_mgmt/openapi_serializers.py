"""作业管理统一 OpenAPI 网关请求契约。"""

from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer
from apps.job_mgmt.constants import OverwriteStrategy


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
        child=serializers.DictField(),
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
