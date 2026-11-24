from django.db import transaction
from rest_framework import serializers

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import Channel, ChannelChoices
from apps.system_mgmt.services.cloud_notify.config import (
    CLOUD_SECRET_FIELDS,
    apply_preserved_secrets,
    declared_parameter_rows,
    fields_preserving_existing_secret,
    masked_config,
    validate_cloud_config,
)
from apps.system_mgmt.services.group_channel_mention import provider_for_group_channel
from apps.system_mgmt.services.notification_channel_pack import (
    apply_pack_secrets,
    declared_pack_parameter_rows,
    encrypt_pack_secrets,
    masked_pack_config,
    notification_capability,
    notification_manifest,
    retain_pack_config,
    validate_pack_channel_config,
)
from apps.system_mgmt.services.notification_tag import assign_channel_tags, channel_tag_tokens, parse_tag_tokens
from apps.system_mgmt.utils.i18n import localized_channel_description

try:
    from apps.system_mgmt.enterprise import nats_notifications
except (ImportError, ModuleNotFoundError):
    nats_notifications = None


class ChannelSerializer(UsernameSerializer):
    tag = serializers.ListField(child=serializers.CharField(), required=False, write_only=True)
    channel_type = serializers.CharField(max_length=30)

    # 各 channel_type 需要加密的字段列表
    ENCRYPT_FIELDS_MAP = {
        ChannelChoices.EMAIL: ["smtp_pwd"],
        ChannelChoices.ENTERPRISE_WECHAT: ["secret", "token", "aes_key"],
        ChannelChoices.ENTERPRISE_WECHAT_BOT: ["webhook_url"],
        ChannelChoices.FEISHU_BOT: ["webhook_url", "sign_secret"],
        ChannelChoices.DINGTALK_BOT: ["webhook_url", "sign_secret"],
        ChannelChoices.CUSTOM_WEBHOOK: ["webhook_url"],
        ChannelChoices.SMS: list(CLOUD_SECRET_FIELDS),
        ChannelChoices.VOICE: list(CLOUD_SECRET_FIELDS),
    }
    CLOUD_CHANNEL_TYPES = {ChannelChoices.SMS, ChannelChoices.VOICE}

    class Meta:
        model = Channel
        fields = (
            "id",
            "name",
            "channel_type",
            "account_association",
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
        if instance.channel_type in self.CLOUD_CHANNEL_TYPES:
            data["config"] = masked_config(instance)
        else:
            manifest = notification_manifest(instance.channel_type)
            if manifest is not None:
                data["config"] = masked_pack_config(instance, manifest)
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
        if config.get("source") == "workflow" or config.get("method_name") == "trigger_orchestration_workflow_by_nats":
            raise serializers.ValidationError({"config": loader.get("error.workflow_channel_readonly")})
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
        manifest = notification_manifest(channel_type)
        if channel_type not in set(ChannelChoices.values) and manifest is None:
            raise serializers.ValidationError({"channel_type": self._loader().get("error.notification_channel_pack_not_loaded")})
        if channel_type == ChannelChoices.NATS:
            config = attrs.get("config", getattr(self.instance, "config", {}) or {})
            self.validate_nats_config(config)
            self.validate_nats_subject_key_unique(config, exclude_channel_id=getattr(self.instance, "pk", None))
        if channel_type in self.CLOUD_CHANNEL_TYPES and "config" in attrs:
            config = attrs.get("config")
            preserved = fields_preserving_existing_secret(config, self.instance.config, self.instance) if self.instance is not None else ()
            cloud_errors = validate_cloud_config(channel_type, config, preserved)
            if cloud_errors:
                raise serializers.ValidationError({"config": self._localize_cloud_errors(cloud_errors)})
            config["parameters"] = declared_parameter_rows(config.get("parameters") or [], config.get("provider"))
        if manifest is not None and "config" in attrs:
            config = attrs.get("config")
            if not isinstance(config, dict):
                raise serializers.ValidationError({"config": self._loader().get("error.notification_channel_config_invalid")})
            config = retain_pack_config(config, manifest)
            preserved = apply_pack_secrets(config, self.instance.config, self.instance, manifest) if self.instance is not None else set()
            pack_errors = validate_pack_channel_config(manifest, config, preserved)
            if pack_errors:
                raise serializers.ValidationError({"config": self._localize_cloud_errors(pack_errors)})
            capability = notification_capability(manifest)
            if capability is not None and capability.delivery == "template":
                config["parameters"] = declared_pack_parameter_rows(config.get("parameters") or [], capability.parameter_mode)
            attrs["config"] = config
            attrs["_pack_preserved_secrets"] = preserved
        if "account_association" in attrs:
            association = attrs.get("account_association")
        else:
            association = getattr(self.instance, "account_association", None) if self.instance else None
        provider = provider_for_group_channel(channel_type)
        if provider is None:
            attrs["account_association"] = None
        elif association is not None and association.integration_instance.provider_key != provider:
            raise serializers.ValidationError({"account_association": self._loader().get("error.account_association_provider_mismatch")})
        return attrs

    def create(self, validated_data):
        pairs = validated_data.pop("tag", [])
        preserved = validated_data.pop("_pack_preserved_secrets", set())
        manifest = notification_manifest(validated_data.get("channel_type"))
        if validated_data.get("config"):
            if manifest is not None:
                encrypt_pack_secrets(validated_data["config"], manifest, preserved)
            else:
                self.encode_config(validated_data)
        with transaction.atomic():
            instance = super().create(validated_data)
            assign_channel_tags(instance, pairs, actor=self._actor())
        return instance

    def update(self, instance, validated_data):
        tag_provided = "tag" in self.initial_data
        pairs = validated_data.pop("tag", [])
        preserved = validated_data.pop("_pack_preserved_secrets", set())
        manifest = notification_manifest(instance.channel_type)
        if validated_data.get("config"):
            if manifest is not None:
                encrypt_pack_secrets(validated_data["config"], manifest, preserved)
            else:
                self.encode_config(validated_data, instance.config, instance.channel_type)
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
    def encode_config(validated_data, old_config=None, channel_type=None):
        if old_config is None:
            old_config = {}
        config = validated_data["config"]
        channel_type = validated_data.get("channel_type", channel_type)
        preserved = set()
        if channel_type in ChannelSerializer.CLOUD_CHANNEL_TYPES:
            preserved = apply_preserved_secrets(config, old_config, Channel)
        encrypt_fields = ChannelSerializer.ENCRYPT_FIELDS_MAP.get(channel_type, [])
        for field in encrypt_fields:
            if field in preserved:
                continue
            Channel.encrypt_field(field, config)
            config.setdefault(field, old_config.get(field, ""))
        validated_data["config"] = config

    def _localize_cloud_errors(self, errors):
        loader = self._loader()
        localized = {}
        for key, value in errors.items():
            localized[key] = loader.get(value) if isinstance(value, str) and value.startswith("error.") else value
        return localized

    def _loader(self):
        request = self.context.get("request")
        locale = getattr(getattr(request, "user", None), "locale", "en") or "en"
        return LanguageLoader(app="system_mgmt", default_lang=locale)
