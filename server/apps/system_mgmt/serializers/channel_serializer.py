from apps.system_mgmt.models import Channel, ChannelChoices
from config.drf.serializers import I18nSerializer


class ChannelSerializer(I18nSerializer):
    class Meta:
        model = Channel
        fields = "__all__"

    def create(self, validated_data):
        if validated_data.get("config"):
            self.encode_config(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data.get("config"):
            self.encode_config(validated_data)
        return super().update(instance, validated_data)

    @staticmethod
    def encode_config(validated_data):
        config = validated_data["config"]
        if validated_data["channel_type"] == "email":
            Channel.encrypt_field("smtp_pwd", config)
        elif validated_data["channel_type"] == "enterprise_wechat":
            Channel.encrypt_field("secret", config)
            Channel.encrypt_field("token", config)
            Channel.encrypt_field("aes_key", config)
        elif validated_data["channel_type"] == ChannelChoices.ENTERPRISE_WECHAT_BOT:
            Channel.encrypt_field("bot_key", config)
        validated_data["config"] = config
