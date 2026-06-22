from copy import deepcopy

from rest_framework import serializers

from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import IntegrationInstance, IntegrationInstanceStatusChoices
from apps.system_mgmt.providers import get_provider_registry


class IntegrationInstanceSerializer(UsernameSerializer):
    provider = serializers.SerializerMethodField()
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

        incoming_config = attrs.get("config")
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
