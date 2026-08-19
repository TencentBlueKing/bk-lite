from rest_framework import serializers

from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import SkillChannel
from apps.opspilot.services.skill_channel_service import copy_usage_team_for_channel


def _mask_config(config: dict) -> dict:
    if not isinstance(config, dict):
        return {}
    masked = {}
    for key, value in config.items():
        if isinstance(value, dict):
            masked[key] = _mask_config(value)
        elif any(s in str(key).lower() for s in ("secret", "token", "aes", "password", "key")) and value:
            masked[key] = "******"
        else:
            masked[key] = value
    return masked


class SkillChannelSerializer(serializers.ModelSerializer):
    callback_path = serializers.SerializerMethodField()
    channel_config = serializers.SerializerMethodField()

    class Meta:
        model = SkillChannel
        fields = [
            "id",
            "skill",
            "name",
            "channel_type",
            "channel_config",
            "enabled",
            "usage_team",
            "callback_path",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "usage_team", "created_at", "updated_at", "callback_path"]

    def get_callback_path(self, instance: SkillChannel) -> str:
        return f"/api/v1/opspilot/skill_channel/{instance.id}/{instance.channel_type}/"

    def get_channel_config(self, instance: SkillChannel):
        return _mask_config(instance.channel_config or {})

    def validate_channel_type(self, value):
        valid = {c.value for c in SkillChannelChoices}
        if value not in valid:
            raise serializers.ValidationError(f"不支持的渠道类型: {value}")
        return value

    def create(self, validated_data):
        skill = validated_data["skill"]
        raw_config = self.initial_data.get("channel_config") or {}
        if not isinstance(raw_config, dict):
            raw_config = {}
        validated_data["channel_config"] = raw_config
        validated_data["usage_team"] = copy_usage_team_for_channel(skill)
        if not validated_data.get("name"):
            validated_data["name"] = dict(SkillChannelChoices.choices).get(validated_data["channel_type"], validated_data["channel_type"])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        raw_config = self.initial_data.get("channel_config")
        if isinstance(raw_config, dict):
            merged = dict(instance.channel_config or {})
            for key, value in raw_config.items():
                if value == "******":
                    continue
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    nested = dict(merged[key])
                    for nk, nv in value.items():
                        if nv == "******":
                            continue
                        nested[nk] = nv
                    merged[key] = nested
                else:
                    merged[key] = value
            validated_data["channel_config"] = merged
        # usage_team 只读：由 Skill 同步权威源维护
        validated_data.pop("usage_team", None)
        return super().update(instance, validated_data)
