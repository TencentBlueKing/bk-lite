"""告警中心对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer, PaginatedRequestSerializer

_ACTIONS = ("assign", "acknowledge", "reassign", "close")


class AlertListRequestSerializer(PaginatedRequestSerializer):
    ordering = serializers.ChoiceField(choices=["created_at", "-created_at"], required=False, default="-created_at")
    title = serializers.CharField(required=False, allow_blank=True, default="")
    content = serializers.CharField(required=False, allow_blank=True, default="")
    alert_id = serializers.CharField(required=False, allow_blank=True, default="")
    activate = serializers.CharField(required=False, allow_blank=True, default="")
    my_alert = serializers.CharField(required=False, allow_blank=True, default="")
    level = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.CharField(required=False, allow_blank=True, default="")
    source_name = serializers.CharField(required=False, allow_blank=True, default="")
    created_at_after = serializers.CharField(required=False, allow_blank=True, default="")
    created_at_before = serializers.CharField(required=False, allow_blank=True, default="")
    incident_id = serializers.CharField(required=False, allow_blank=True, default="")
    has_incident = serializers.CharField(required=False, allow_blank=True, default="")
    rule_id = serializers.CharField(required=False, allow_blank=True, default="")
    resource_type = serializers.CharField(required=False, allow_blank=True, default="")
    resource_id = serializers.CharField(required=False, allow_blank=True, default="")


class AlertIdRequestSerializer(OpenAPIRequestSerializer):
    alert_id = serializers.CharField()


class AlertEventsRequestSerializer(PaginatedRequestSerializer):
    alert_id = serializers.CharField()


class AlertAssignRequestSerializer(OpenAPIRequestSerializer):
    alert_id = serializers.CharField()
    assignee = serializers.ListField(child=serializers.CharField(), min_length=1)
    assignment_id = serializers.IntegerField(required=False)


class AlertAcknowledgeRequestSerializer(OpenAPIRequestSerializer):
    alert_id = serializers.CharField()


class AlertCloseRequestSerializer(OpenAPIRequestSerializer):
    alert_id = serializers.CharField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AlertBatchActionRequestSerializer(OpenAPIRequestSerializer):
    action = serializers.ChoiceField(choices=_ACTIONS)
    alert_ids = serializers.ListField(child=serializers.CharField(), min_length=1, max_length=100)
    assignee = serializers.ListField(child=serializers.CharField(), required=False)
    assignment_id = serializers.IntegerField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
