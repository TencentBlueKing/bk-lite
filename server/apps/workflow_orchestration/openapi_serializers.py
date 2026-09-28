from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer


class WorkflowTriggerInvokeRequestSerializer(OpenAPIRequestSerializer):
    trigger_id = serializers.UUIDField()
    idempotency_key = serializers.CharField(max_length=128)
    inputs = serializers.JSONField(required=False, default=dict)

    def validate_inputs(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("必须是 JSON 对象")
        return value


class WorkflowWebhookTestRequestSerializer(OpenAPIRequestSerializer):
    token = serializers.CharField(max_length=2048, trim_whitespace=True)
    body = serializers.JSONField(required=False, default=dict)

    def validate_body(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("必须是 JSON 对象")
        return value
