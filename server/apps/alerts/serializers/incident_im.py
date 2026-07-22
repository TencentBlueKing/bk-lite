from rest_framework import serializers

from apps.alerts.models import IncidentIMMember
from apps.system_mgmt.models import User


class IncidentIMGroupCreateSerializer(serializers.Serializer):
    channel_id = serializers.IntegerField(min_value=1)
    group_name = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)
    owner_username = serializers.CharField(max_length=32)
    continuous_sync_enabled = serializers.BooleanField(default=True)


class IncidentIMGroupSettingsSerializer(serializers.Serializer):
    continuous_sync_enabled = serializers.BooleanField()


class IncidentIMGroupUnlinkSerializer(serializers.Serializer):
    group_name = serializers.CharField(max_length=255)


class IncidentIMMemberSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    error_code = serializers.CharField(source="last_error_code")
    error_message = serializers.CharField(source="last_error_message")

    class Meta:
        model = IncidentIMMember
        fields = (
            "username",
            "display_name",
            "role",
            "mapping_status",
            "sync_status",
            "error_code",
            "error_message",
        )

    def get_display_name(self, obj):
        display_names = self.context.get("display_names", {})
        return display_names.get(obj.username, obj.username)


def serialize_resolved_member(member):
    return {
        "username": member.username,
        "display_name": member.display_name,
        "role": member.role,
        "mapping_status": member.mapping_status,
        "error_code": member.error_code,
        "error_message": member.error_message,
    }


def member_display_names(members):
    usernames = [member.username for member in members]
    return dict(User.objects.filter(username__in=usernames).values_list("username", "display_name"))
