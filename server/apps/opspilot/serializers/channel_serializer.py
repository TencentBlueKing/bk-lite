from rest_framework import serializers

from apps.core.utils.serializers import UsernameSerializer
from apps.opspilot.models import Channel


class ChannelSerializer(UsernameSerializer):
    channel_config = serializers.SerializerMethodField()

    class Meta:
        model = Channel
        # 显式字段列表，等价于原 "__all__"（id + MaintainerInfo 字段 + 业务字段），
        # 唯一区别是 channel_config 在读取时被脱敏，避免明文/密文密钥外泄。
        fields = [
            "id",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "name",
            "channel_type",
            "channel_config",
            "enabled",
        ]

    def get_channel_config(self, instance):
        """读取时对密钥字段脱敏，写入仍走模型字段（write_only 语义通过 SerializerMethodField 实现）。"""
        if not instance.channel_config:
            return instance.channel_config
        return instance.format_channel_config()

    def to_internal_value(self, data):
        # SerializerMethodField 默认只读，这里把传入的 channel_config 透传到模型字段，保持写入行为不变。
        validated = super().to_internal_value(data)
        if "channel_config" in data:
            validated["channel_config"] = data["channel_config"]
        return validated
