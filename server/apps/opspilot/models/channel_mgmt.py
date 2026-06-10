from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_yaml_field import YAMLField

from apps.core.mixinx import EncryptMixin
from apps.core.models.maintainer_info import MaintainerInfo
from apps.opspilot.enum import ChannelChoices


class Channel(MaintainerInfo, EncryptMixin):
    name = models.CharField(max_length=100, verbose_name=_("name"))
    channel_type = models.CharField(max_length=100, choices=ChannelChoices.choices, verbose_name=_("channel type"))
    channel_config = YAMLField(verbose_name=_("channel config"), blank=True, null=True)
    enabled = models.BooleanField(default=False, verbose_name=_("enabled"))

    # 渠道加密字段配置映射（与 BotChannel 保持一致，符合开闭原则）
    CHANNEL_ENCRYPT_CONFIG = {
        ChannelChoices.GITLAB: {
            "key": "channels.gitlab_review_channel.GitlabReviewChannel",
            "fields": ["secret_token"],
        },
        ChannelChoices.DING_TALK: {
            "key": "channels.dingtalk_channel.DingTalkChannel",
            "fields": ["client_secret"],
        },
        ChannelChoices.ENTERPRISE_WECHAT: {
            "key": "channels.enterprise_wechat_channel.EnterpriseWechatChannel",
            "fields": ["secret_token", "aes_key", "secret", "token"],
        },
        ChannelChoices.WECHAT_OFFICIAL_ACCOUNT: {
            "key": "channels.wechat_official_account_channel.WechatOfficialAccountChannel",
            "fields": ["aes_key", "secret", "token"],
        },
        ChannelChoices.ENTERPRISE_WECHAT_BOT: {
            "key": "channels.enterprise_wechat_bot_channel.EnterpriseWechatBotChannel",
            "fields": ["secret_token"],
        },
    }

    class Meta:
        verbose_name = _("channel")
        verbose_name_plural = verbose_name
        db_table = "channel_mgmt_channel"

    def __str__(self):
        return self.name

    def _process_channel_encryption(self, encrypt=True):
        """
        处理渠道配置的加密/解密

        Args:
            encrypt: True 表示加密，False 表示解密
        """
        if self.channel_config is None:
            return

        config = self.CHANNEL_ENCRYPT_CONFIG.get(self.channel_type)
        if not config:
            return

        channel_key = config["key"]
        fields = config["fields"]
        channel_data = self.channel_config.get(channel_key)

        if not channel_data:
            return

        process_func = self.encrypt_field if encrypt else self.decrypt_field

        for field in fields:
            process_func(field, channel_data)

    def save(self, *args, **kwargs):
        if self.channel_config is None:
            super().save(*args, **kwargs)
            return

        # 先解密（避免重复加密）
        self._process_channel_encryption(encrypt=False)
        # 再加密
        self._process_channel_encryption(encrypt=True)

        super().save(*args, **kwargs)

    @cached_property
    def decrypted_channel_config(self):
        """获取解密后的渠道配置"""
        if self.channel_config is None:
            return None

        decrypted_config = self.channel_config.copy()
        config = self.CHANNEL_ENCRYPT_CONFIG.get(self.channel_type)

        if not config:
            return decrypted_config

        channel_key = config["key"]
        fields = config["fields"]
        channel_data = decrypted_config.get(channel_key)

        if channel_data:
            for field in fields:
                self.decrypt_field(field, channel_data)

        return decrypted_config

    def format_channel_config(self):
        return_data = {}
        keys = ["secret", "token", "aes_key", "client_secret"]
        for key, value in self.channel_config.items():
            return_data[key] = {i: "******" if v and i in keys else v for i, v in value.items()}
        return return_data
