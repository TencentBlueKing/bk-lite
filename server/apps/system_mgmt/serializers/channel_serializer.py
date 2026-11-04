from django.db import transaction
from rest_framework import serializers

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import Channel, ChannelChoices
from apps.system_mgmt.services.notification_tag import assign_channel_tags, channel_tag_tokens, parse_tag_tokens
from apps.system_mgmt.utils.i18n import localized_channel_description

try:
    from apps.system_mgmt.enterprise import nats_notifications
except (ImportError, ModuleNotFoundError):
    nats_notifications = None


class ChannelSerializer(UsernameSerializer):
    tag = serializers.ListField(child=serializers.CharField(), required=False, write_only=True)

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
        fields = (
            "id",
            "name",
            "channel_type",
            "config",
            "description",
            "team",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "tag",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        locale = getattr(getattr(request, "user", None), "locale", None)
        data["description"] = localized_channel_description(data.get("description"), locale)
        data["tag"] = channel_tag_tokens(instance)
        return data

    def validate_tag(self, value):
        return parse_tag_tokens(value)

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
        pairs = validated_data.pop("tag", [])
        if validated_data.get("config"):
            self.encode_config(validated_data)
        with transaction.atomic():
            instance = super().create(validated_data)
            assign_channel_tags(instance, pairs, actor=self._actor())
        return instance

    def update(self, instance, validated_data):
        tag_provided = "tag" in self.initial_data
        pairs = validated_data.pop("tag", [])
        if validated_data.get("config"):
            self.encode_config(validated_data, instance.config)
        else:
            validated_data["config"] = instance.config
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if tag_provided:
                assign_channel_tags(instance, pairs, actor=self._actor())
        return instance

    def _actor(self):
        return getattr(self.context.get("request"), "user", None)

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
