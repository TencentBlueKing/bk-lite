from copy import deepcopy

from rest_framework import serializers

from apps.core.services.login_auth_request_service import get_login_auth_callback_uri
from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import IntegrationInstance, IntegrationInstanceStatusChoices
from apps.system_mgmt.providers import get_provider_registry
from apps.system_mgmt.services.capability_contract_service import validate_integration_capability_state


class IntegrationInstanceSerializer(UsernameSerializer):
    provider = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    login_auth_callback_url = serializers.SerializerMethodField()
    is_draft = serializers.BooleanField(write_only=True, required=False, default=False)
    config_scope = serializers.CharField(write_only=True, required=False, allow_blank=True, default="")

    class Meta:
        model = IntegrationInstance
        fields = "__all__"

    def get_provider(self, obj):
        manifest = get_provider_registry().get(obj.provider_key)
        if manifest is None:
            return {"key": obj.provider_key, "name": obj.provider_key}
        return {"key": manifest.key, "name": manifest.name}

    def get_display_name(self, obj):
        manifest = get_provider_registry().get(obj.provider_key)
        provider_name = manifest.name if manifest else obj.provider_key
        return f"{obj.name}({provider_name})"

    def get_login_auth_callback_url(self, obj):
        capability_status = obj.capability_status or {}
        capability_enabled = obj.capability_enabled or {}
        has_login_auth = "login_auth" in capability_status or "login_auth" in capability_enabled
        if not has_login_auth:
            return ""
        request = self.context.get("request")
        raw_origin = self.context.get("redirect_origin")
        redirect_origin = raw_origin if isinstance(raw_origin, str) and raw_origin.strip() else None
        return get_login_auth_callback_uri(request=request, redirect_origin=redirect_origin)

    def validate(self, attrs):
        provider_key = attrs.get("provider_key") or getattr(self.instance, "provider_key", "")
        manifest = get_provider_registry().get(provider_key)
        if manifest is None:
            raise serializers.ValidationError({"provider_key": "Unknown provider"})
        is_draft = attrs.pop("is_draft", False)
        config_scope = attrs.pop("config_scope", "")
        attrs["_is_draft"] = is_draft
        attrs["_config_scope"] = config_scope

        if self.instance and "provider_key" in attrs and attrs["provider_key"] != self.instance.provider_key:
            raise serializers.ValidationError({"provider_key": "provider_key cannot be changed after creation"})

        contract_errors = {}
        incoming_config = attrs.get("config")
        if incoming_config is not None and not isinstance(incoming_config, dict):
            contract_errors["config"] = "Config must be an object"
        contract_errors.update(
            validate_integration_capability_state(
                manifest,
                capability_status=attrs.get("capability_status"),
                capability_enabled=attrs.get("capability_enabled"),
            )
        )

        if contract_errors:
            raise serializers.ValidationError(contract_errors)

        old_runtime_config = self.instance.get_runtime_config() if self.instance else {}
        effective_config = deepcopy(old_runtime_config)
        if incoming_config is not None:
            for key, value in incoming_config.items():
                if value not in (None, ""):
                    effective_config[key] = value

        if not (self.instance is None and is_draft):
            required_fields = manifest.get_all_connection_fields() if self.instance is None else manifest.get_scoped_connection_fields(config_scope)
            missing_required_fields = []
            for field in required_fields:
                if field.required and not effective_config.get(field.key):
                    missing_required_fields.append(field.key)

            if missing_required_fields:
                raise serializers.ValidationError({"config": f"Missing required config fields: {', '.join(missing_required_fields)}"})

        return attrs

    def create(self, validated_data):
        validated_data.pop("_is_draft", None)
        validated_data.pop("_config_scope", None)
        manifest = get_provider_registry().get(validated_data["provider_key"])
        if manifest is None:
            raise serializers.ValidationError({"provider_key": "Unknown provider"})

        config = self._encode_config(manifest, validated_data.get("config") or {}, {})
        validated_data["config"] = config
        validated_data["capability_enabled"] = {
            capability.key: True for capability in manifest.capabilities
        }
        validated_data["capability_status"] = {
            capability.key: IntegrationInstanceStatusChoices.PENDING_VERIFICATION for capability in manifest.capabilities
        }
        validated_data["status"] = IntegrationInstanceStatusChoices.PENDING_VERIFICATION
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("_is_draft", None)
        validated_data.pop("_config_scope", None)
        manifest = get_provider_registry().get(instance.provider_key)
        if manifest is None:
            raise serializers.ValidationError({"provider_key": "Unknown provider"})

        incoming_config = validated_data.get("config")
        if incoming_config is None:
            validated_data["config"] = instance.config
            return super().update(instance, validated_data)

        old_runtime_config = instance.get_runtime_config()
        changed_capabilities = set()
        for field in manifest.instance_template:
            new_value = incoming_config.get(field.key, old_runtime_config.get(field.key))
            if new_value in (None, ""):
                new_value = old_runtime_config.get(field.key)
            if old_runtime_config.get(field.key) != new_value:
                changed_capabilities.update(field.reset_capabilities)

        for capability in manifest.capabilities:
            for field in capability.connection_template:
                new_value = incoming_config.get(field.key, old_runtime_config.get(field.key))
                if new_value in (None, ""):
                    new_value = old_runtime_config.get(field.key)
                if old_runtime_config.get(field.key) != new_value:
                    changed_capabilities.update(field.reset_capabilities or [capability.key])

        validated_data["config"] = self._encode_config(manifest, incoming_config, instance.config)
        if changed_capabilities:
            capability_status = deepcopy(instance.capability_status or {})
            for capability_key in changed_capabilities:
                capability_status[capability_key] = IntegrationInstanceStatusChoices.PENDING_VERIFICATION
            validated_data["capability_status"] = capability_status
            validated_data["status"] = IntegrationInstanceStatusChoices.PENDING_VERIFICATION
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["config"] = instance.get_masked_config()
        return data

    @staticmethod
    def _encode_config(manifest, new_config, old_config):
        config = deepcopy(old_config or {})
        config.update(new_config or {})
        for field in manifest.get_secret_fields():
            value = (new_config or {}).get(field.key)
            if value not in (None, ""):
                IntegrationInstance.encrypt_field(field.key, config)
            else:
                config[field.key] = (old_config or {}).get(field.key, "")
        return config
