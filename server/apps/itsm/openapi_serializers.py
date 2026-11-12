from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer, PaginatedRequestSerializer


class TicketListRequestSerializer(PaginatedRequestSerializer):
    pass


class TicketCreateRequestSerializer(OpenAPIRequestSerializer):
    workflow_key = serializers.CharField()
    title = serializers.CharField()


class TicketOperateRequestSerializer(OpenAPIRequestSerializer):
    ticket_id = serializers.IntegerField()
    action = serializers.CharField()
    task_id = serializers.IntegerField(required=False)


class IdListRequestSerializer(PaginatedRequestSerializer):
    pass
