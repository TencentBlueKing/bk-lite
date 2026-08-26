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


def _validate_target_source_ids(attrs):
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
        return _validate_target_source_ids(attrs)


class ScriptExecuteParamSerializer(OpenAPIRequestSerializer):
    """脚本位置参数；值允许为空以保留占位。"""

    name = serializers.CharField(max_length=128)
    value = serializers.CharField(required=False, allow_blank=True, default="")


class ScriptExecuteRequestSerializer(OpenAPIRequestSerializer):
    """可信身份脚本执行请求；团队身份只允许由网关注入。"""

    name = serializers.CharField(max_length=256)
    target_source = serializers.ChoiceField(choices=["node_mgmt", "manual"])
    target_list = serializers.ListField(
        child=FileDistributeTargetSerializer(),
        min_length=1,
        max_length=500,
    )
    script_type = serializers.ChoiceField(choices=["shell", "python", "powershell", "bat"])
    script_content = serializers.CharField()
    params = serializers.ListField(
        child=ScriptExecuteParamSerializer(),
        required=False,
        default=list,
        max_length=100,
    )
    timeout = serializers.IntegerField(required=False, default=600, min_value=1, max_value=86400)

    def validate(self, attrs):
        return _validate_target_source_ids(attrs)


class JobStatusRequestSerializer(OpenAPIRequestSerializer):
    """批量查询作业状态；团队身份只允许由网关注入。"""

    task_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        max_length=100,
    )


class JobDetailRequestSerializer(OpenAPIRequestSerializer):
    """查询单个作业详情；团队身份只允许由网关注入。"""

    task_id = serializers.IntegerField(min_value=1)


class TargetListV2RequestSerializer(OpenAPIRequestSerializer):
    """统一网关目标列表 v2 请求；调用方身份与团队只由网关注入。"""

    name = serializers.CharField(required=False, allow_blank=True, max_length=128, default="")
    ip = serializers.CharField(required=False, allow_blank=True, max_length=45, default="")
    os_type = serializers.ChoiceField(required=False, allow_blank=True, choices=["", "linux", "windows"], default="")
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)
    cursor = serializers.IntegerField(required=False, min_value=1, allow_null=True, default=None)
