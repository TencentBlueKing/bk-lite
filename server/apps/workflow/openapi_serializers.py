from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer
from apps.workflow.services.validation_messages import render_known_message


class WorkflowTriggerInvokeRequestSerializer(OpenAPIRequestSerializer):
    trigger_id = serializers.UUIDField()
    idempotency_key = serializers.CharField(max_length=128)
    inputs = serializers.DictField(required=False, default=dict)

    def validate_inputs(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(render_known_message(self.context.get("request"), "必须是 JSON 对象"))
        return value


class WorkflowWebhookTestRequestSerializer(OpenAPIRequestSerializer):
    token = serializers.CharField(max_length=2048, trim_whitespace=True)
    body = serializers.DictField(required=False, default=dict)

    def validate_body(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(render_known_message(self.context.get("request"), "必须是 JSON 对象"))
        return value


class WorkflowListRequestSerializer(OpenAPIRequestSerializer):
    """分页查询当前授权组织可执行的已发布流程；团队身份只允许由网关注入。"""

    name = serializers.CharField(required=False, allow_blank=True, default="", max_length=120)
    page = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=20)

    def validate_page(self, value):
        return max(int(value), 1)

    def validate_page_size(self, value):
        return min(max(int(value), 1), 100)


class WorkflowListItemSerializer(OpenAPIRequestSerializer):
    """编排中心流程条目；id 用字符串，方便第三方把选项 key 回传执行接口。"""

    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    current_version = serializers.IntegerField()
    enabled = serializers.BooleanField()


class WorkflowListResponseSerializer(OpenAPIRequestSerializer):
    count = serializers.IntegerField()
    items = WorkflowListItemSerializer(many=True)


class WorkflowAsyncCallbackContextSerializer(OpenAPIRequestSerializer):
    callback_url = serializers.URLField(max_length=1024)
    callback_token = serializers.CharField(max_length=256, trim_whitespace=False)
    operator = serializers.CharField(max_length=128)
    timeout = serializers.IntegerField(min_value=1, max_value=86400)


class WorkflowExecuteAsyncRequestSerializer(OpenAPIRequestSerializer):
    """按流程 ID 异步启动编排中心流程；完成后按 callback_context 回传。"""

    workflow_id = serializers.CharField(max_length=32)
    inputs = serializers.DictField(required=False, default=dict)
    callback_context = WorkflowAsyncCallbackContextSerializer()

    def validate_inputs(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(render_known_message(self.context.get("request"), "必须是 JSON 对象"))
        return value


class WorkflowExecuteAsyncResponseSerializer(OpenAPIRequestSerializer):
    accepted = serializers.BooleanField()
    execution_id = serializers.CharField()
