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


class VmwareCatalogRequestSerializer(OpenAPIRequestSerializer):
    preview = serializers.BooleanField(required=False, default=False)
    profile = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
    kind = serializers.ChoiceField(choices=("flavor", "template", "network", "disk_policy", "disk_size", "quantity"))
    disk_policy_id = serializers.CharField(required=False, max_length=200)
    keyword = serializers.CharField(required=False, allow_blank=True, max_length=100)
    page = serializers.IntegerField(required=False, min_value=1)
