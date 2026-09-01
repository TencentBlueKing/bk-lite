from rest_framework import serializers

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import Channel, ChannelChoices

try:
    from apps.system_mgmt.enterprise import nats_notifications
except (ImportError, ModuleNotFoundError):
    nats_notifications = None


class ChannelSerializer(UsernameSerializer):
    # 各 channel_type 需要加密的字段列表
    ENCRYPT_FIELDS_MAP = {
        ChannelChoices.EMAIL: ["smtp_pwd"],
        ChannelChoices.ENTERPRISE_WECHAT: ["secret", "token", "aes_key"],
        ChannelChoices.ENTERPRISE_WECHAT_BOT: ["webhook_url"],
        ChannelChoices.FEISHU_BOT: ["webhook_url", "sign_secret"],
        ChannelChoices.DINGTALK_BOT: ["webhook_url", "sign_secret"],
        ChannelChoices.CUSTOM_WEBHOOK: ["webhook_url"],
    }

    class Meta:
        model = Channel
        fields = "__all__"

    def validate_team(self, value):
        if isinstance(value, (int, str)):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            raise serializers.ValidationError(self._loader().get("error.channel_team_required"))

        team_ids = []
        for team_id in value:
            try:
                team_ids.append(int(team_id))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(self._loader().get("error.channel_team_required")) from exc
        return team_ids

    def validate_nats_config(self, config):
        loader = self._loader()
        if not isinstance(config, dict):
            raise serializers.ValidationError({"config": loader.get("error.nats_config_must_be_object")})
        if "supports_notify_person" in config and not isinstance(config["supports_notify_person"], bool):
            raise serializers.ValidationError({"config": {"supports_notify_person": loader.get("error.nats_supports_notify_person_boolean")}})
        if nats_notifications is not None and nats_notifications.handles_config(config):
            return nats_notifications.validate_config(config)
        if config.get("nats_mode") not in (None, "request_reply"):
            raise serializers.ValidationError({"config": {"nats_mode": loader.get("error.nats_mode_unsupported")}})
        return config

    def validate_nats_subject_key_unique(self, config, exclude_channel_id=None):
        if nats_notifications is None or not nats_notifications.handles_config(config):
            return

        subject_key = config.get("subject_key")
        channels = Channel.objects.filter(
            channel_type=ChannelChoices.NATS,
            config__nats_mode="event_publish",
            config__subject_key=subject_key,
        )
        if exclude_channel_id is not None:
            channels = channels.exclude(pk=exclude_channel_id)
        if channels.exists():
            raise serializers.ValidationError({"config": {"subject_key": self._loader().get("error.nats_subject_key_in_use")}})

    def validate(self, attrs):
        attrs = super().validate(attrs)
        channel_type = attrs.get("channel_type", getattr(self.instance, "channel_type", None))
        if channel_type == ChannelChoices.NATS:
            config = attrs.get("config", getattr(self.instance, "config", {}) or {})
            self.validate_nats_config(config)
            self.validate_nats_subject_key_unique(config, exclude_channel_id=getattr(self.instance, "pk", None))
        return attrs

    def create(self, validated_data):
        if validated_data.get("config"):
            self.encode_config(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data.get("config"):
            self.encode_config(validated_data, instance.config)
        else:
            validated_data["config"] = instance.config
        return super().update(instance, validated_data)

    @staticmethod
    def encode_config(validated_data, old_config=None):
        if old_config is None:
            old_config = {}
        config = validated_data["config"]
        encrypt_fields = ChannelSerializer.ENCRYPT_FIELDS_MAP.get(validated_data["channel_type"], [])
        for field in encrypt_fields:
            Channel.encrypt_field(field, config)
            config.setdefault(field, old_config.get(field, ""))
        validated_data["config"] = config

    def _loader(self):
        request = self.context.get("request")
        locale = getattr(getattr(request, "user", None), "locale", "en") or "en"
        return LanguageLoader(app="system_mgmt", default_lang=locale)
