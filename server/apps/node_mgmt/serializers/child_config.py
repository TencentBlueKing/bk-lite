from rest_framework import serializers

from apps.node_mgmt.models.sidecar import ChildConfig, CollectorConfiguration

_REDACTED_ENV = "***"


def _vault_env_keys(config_id):
    from apps.monitor.services.vault_credential.binding import managed_env_keys_for_child

    return managed_env_keys_for_child(config_id)


def _retain_vault_env(original, incoming, keys):
    managed = set(keys or [])
    original = original or {}
    if not isinstance(incoming, dict):
        return {key: original[key] for key in managed if key in original}
    retained = {}
    for key, value in incoming.items():
        if key in managed and value in (None, "", _REDACTED_ENV):
            continue
        retained[key] = value
    for key in managed:
        if key not in retained and key in original:
            retained[key] = original[key]
    return retained


class ChildConfigSerializer(serializers.ModelSerializer):
    collector_config = serializers.PrimaryKeyRelatedField(queryset=CollectorConfiguration.objects.all())

    def to_representation(self, instance):
        data = super().to_representation(instance)
        keys = _vault_env_keys(instance.id)
        env_config = data.get("env_config")
        if keys and isinstance(env_config, dict):
            data["env_config"] = {key: ("***" if key in keys and value not in (None, "") else value) for key, value in env_config.items()}
        return data

    def update(self, instance, validated_data):
        keys = _vault_env_keys(instance.id)
        if keys is not None:
            if "env_config" in validated_data:
                validated_data["env_config"] = _retain_vault_env(instance.env_config or {}, validated_data.get("env_config"), keys)
            if validated_data.get("content") == "***":
                validated_data.pop("content", None)
        return super().update(instance, validated_data)

    class Meta:
        model = ChildConfig
        fields = [
            "id",
            "collect_type",
            "config_type",
            "content",
            "collector_config",
            "env_config",
            "sort_order",
            "config_section",
        ]
        read_only_fields = ["id"]
