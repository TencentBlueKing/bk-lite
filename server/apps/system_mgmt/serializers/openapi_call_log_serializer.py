from rest_framework import serializers

from apps.system_mgmt.models import OpenAPICallLog


class OpenAPICallLogSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(read_only=True, allow_null=True)

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
        ]
        read_only_fields = fields
