from rest_framework import serializers

from apps.system_mgmt.models import OpenAPICallLog
from apps.system_mgmt.utils.openapi_call_result import derive_openapi_call_result


class OpenAPICallLogSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(read_only=True, allow_null=True)
    call_result = serializers.SerializerMethodField()

    class Meta:
        model = OpenAPICallLog
        fields = [
            "id",
            "created_at",
            "source_ip",
            "username",
            "team_id",
            "team_name",
            "credential_type",
            "token_name",
            "system_id",
            "api_kind",
            "method",
            "path",
            "http_status",
            "error_code",
            "call_result",
        ]
        read_only_fields = fields

    def get_call_result(self, obj):
        return derive_openapi_call_result(obj.api_kind, obj.http_status, obj.error_code)
