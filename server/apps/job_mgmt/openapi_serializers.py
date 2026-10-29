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
    """可信身份脚本执行请求；团队身份只允许由网关注入。

    两种互斥入口：
    - 内联：name + script_type + script_content
    - 脚本库：script_id（服务端按授权组织解析内容，忽略调用方传入的脚本正文）
    """

    name = serializers.CharField(required=False, allow_blank=True, default="", max_length=256)
    target_source = serializers.ChoiceField(choices=["node_mgmt", "manual"])
    target_list = serializers.ListField(
        child=FileDistributeTargetSerializer(),
        min_length=1,
        max_length=500,
    )
    script_id = serializers.IntegerField(required=False, min_value=1)
    script_type = serializers.ChoiceField(
        required=False,
        allow_blank=True,
        default="",
        choices=["shell", "python", "powershell", "bat"],
    )
    script_content = serializers.CharField(required=False, allow_blank=True, default="")
    params = serializers.ListField(
        child=ScriptExecuteParamSerializer(),
        required=False,
        default=list,
        max_length=100,
    )
    timeout = serializers.IntegerField(required=False, default=600, min_value=1, max_value=86400)

    def validate(self, attrs):
        if attrs.get("script_id"):
            return _validate_target_source_ids(attrs)
        errors = {}
        if not (attrs.get("name") or "").strip():
            errors["name"] = ["required"]
        if not attrs.get("script_type"):
            errors["script_type"] = ["required"]
        if not attrs.get("script_content"):
            errors["script_content"] = ["required"]
        if errors:
            raise serializers.ValidationError(errors)
        return _validate_target_source_ids(attrs)


class AsyncCallbackContextSerializer(OpenAPIRequestSerializer):
    """调用方提供的异步完成回调上下文；令牌原样保存，不 trim。"""

    callback_url = serializers.URLField(max_length=1024)
    callback_token = serializers.CharField(max_length=256, trim_whitespace=False)
    operator = serializers.CharField(max_length=128)
    timeout = serializers.IntegerField(min_value=1, max_value=86400)


class AsyncScriptExecuteRequestSerializer(ScriptExecuteRequestSerializer):
    """脚本执行异步提交；完成后按 callback_context 回传结果。"""

    callback_context = AsyncCallbackContextSerializer()


class AsyncAcceptedSerializer(OpenAPIRequestSerializer):
    """异步提交首次受理响应。"""

    accepted = serializers.BooleanField()
    execution_id = serializers.CharField()


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


class ScriptListRequestSerializer(OpenAPIRequestSerializer):
    """分页查询当前授权组织的脚本库；团队身份只允许由网关注入。"""

    name = serializers.CharField(required=False, allow_blank=True, default="", max_length=128)
    page = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=20)

    def validate_page(self, value):
        return max(int(value), 1)

    def validate_page_size(self, value):
        return min(max(int(value), 1), 100)


class ScriptListItemSerializer(OpenAPIRequestSerializer):
    """脚本库条目；id 用字符串，方便第三方把选项 key 直接回传执行接口。不含脚本内容。"""

    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    script_type = serializers.CharField()
    timeout = serializers.IntegerField()
    is_built_in = serializers.BooleanField()


class ScriptListResponseSerializer(OpenAPIRequestSerializer):
    """脚本库分页结果。"""

    count = serializers.IntegerField()
    items = ScriptListItemSerializer(many=True)
