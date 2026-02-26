from apps.core.utils.serializers import UsernameSerializer
from apps.system_mgmt.models import Channel, ChannelChoices


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
