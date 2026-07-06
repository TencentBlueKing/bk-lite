from rest_framework import serializers

from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import (
    IntegrationInstanceStatusChoices,
    LoginAuthBinding,
    LoginAuthBindingUnmatchedActionChoices,
)


class LoginAuthBindingSerializer(UsernameSerializer):
    integration_instance_name = serializers.SerializerMethodField()
    builtin_provider_key = "bk_lite_builtin"

    class Meta:
        model = LoginAuthBinding
        fields = "__all__"

    def get_integration_instance_name(self, obj):
        return obj.integration_instance.name if obj.integration_instance_id else ""

    def validate(self, attrs):
        if self.instance and self.instance.integration_instance.provider_key == self.builtin_provider_key:
            next_instance = attrs.get("integration_instance", self.instance.integration_instance)
            if next_instance.id != self.instance.integration_instance_id:
                raise serializers.ValidationError({"integration_instance": "Built-in login auth binding cannot change integration instance"})

            next_enabled = attrs.get("enabled", self.instance.enabled)
            if not next_enabled:
                raise serializers.ValidationError({"enabled": "Built-in login auth binding cannot be disabled"})

            protected_fields = (
                "external_field",
                "platform_field",
                "unmatched_user_action",
                "default_group_name",
            )
            for field_name in protected_fields:
                if field_name in attrs and attrs[field_name] != getattr(self.instance, field_name):
                    raise serializers.ValidationError({field_name: "Built-in login auth binding field cannot be modified"})

        instance = attrs.get("integration_instance") or getattr(self.instance, "integration_instance", None)
        if instance is None:
            raise serializers.ValidationError({"integration_instance": "Integration instance is required"})

        if instance.provider_key == "":
            raise serializers.ValidationError({"integration_instance": "Integration instance provider is invalid"})

        if instance.status != IntegrationInstanceStatusChoices.READY or instance.capability_status.get("login_auth") != IntegrationInstanceStatusChoices.READY:
            raise serializers.ValidationError({"integration_instance": "Integration instance login_auth capability is not ready"})

        unmatched_action = attrs.get("unmatched_user_action") or getattr(
            self.instance, "unmatched_user_action", LoginAuthBindingUnmatchedActionChoices.DENY
        )
        default_group_name = attrs.get("default_group_name") or getattr(self.instance, "default_group_name", "")
        if unmatched_action == LoginAuthBindingUnmatchedActionChoices.CREATE and not default_group_name:
            raise serializers.ValidationError({"default_group_name": "Default group name is required when unmatched user action is create"})

        return attrs

    def create(self, validated_data):
        if validated_data.get("order", 0) == 0:
            max_order = LoginAuthBinding.objects.order_by("-order").values_list("order", flat=True).first() or 0
            validated_data["order"] = max_order + 1
        return super().create(validated_data)
