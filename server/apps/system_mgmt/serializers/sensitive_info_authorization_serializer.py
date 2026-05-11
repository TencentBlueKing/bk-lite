from rest_framework import serializers

from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import SensitiveInfoAuthorization, User
from apps.system_mgmt.models.sensitive_info_authorization import (
    SENSITIVE_TYPE_LABELS,
    get_authorized_types_text,
    normalize_sensitive_types,
)


class SensitiveInfoAuthorizationSerializer(UsernameSerializer):
    sensitive_types = serializers.ListField(child=serializers.ChoiceField(choices=tuple(SENSITIVE_TYPE_LABELS.keys())))
    display_name = serializers.SerializerMethodField()
    authorized_types_text = serializers.SerializerMethodField()
    authorized_at = serializers.SerializerMethodField()

    class Meta:
        model = SensitiveInfoAuthorization
        fields = [
            "id",
            "username",
            "domain",
            "sensitive_types",
            "remark",
            "display_name",
            "authorized_types_text",
            "authorized_at",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "updated_by_domain",
        ]

    def __init__(self, instance=None, data=serializers.empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        self.display_name_map = {
            f"{user['username']}@{user['domain']}": user["display_name"]
            for user in User.objects.all().values("username", "domain", "display_name")
        }

    def validate_sensitive_types(self, value):
        normalized = normalize_sensitive_types(value)
        if not normalized:
            raise serializers.ValidationError("sensitive_types is required")
        return normalized

    def get_display_name(self, obj):
        return self.display_name_map.get(f"{obj.username}@{obj.domain}", "")

    def get_authorized_types_text(self, obj):
        return get_authorized_types_text(obj.sensitive_types)

    def get_authorized_at(self, obj):
        return obj.created_at
