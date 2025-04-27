import binascii
import os

from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_yaml_field import YAMLField

from apps.core.mixinx import EncryptMixin
from apps.core.models.maintainer_info import MaintainerInfo
from apps.opspilot.enum import ChannelChoices


class Bot(MaintainerInfo):
    name = models.CharField(max_length=255, verbose_name="名称")
    introduction = models.TextField(blank=True, null=True, verbose_name="描述")
    team = models.JSONField(default=list)
    channels = models.JSONField(default=list)
    rasa_model = models.ForeignKey("RasaModel", on_delete=models.CASCADE, verbose_name="模型", blank=True, null=True)
    llm_skills = models.ManyToManyField("LLMSkill", verbose_name="LLM技能", blank=True)
    enable_bot_domain = models.BooleanField(verbose_name="启用域名", default=False)
    bot_domain = models.CharField(max_length=255, verbose_name="域名", blank=True, null=True)

    enable_node_port = models.BooleanField(verbose_name="启用端口映射", default=False)
    node_port = models.IntegerField(verbose_name="端口映射", default=5005)
    online = models.BooleanField(verbose_name="是否上线", default=False)
    enable_ssl = models.BooleanField(verbose_name="启用SSL", default=False)
    api_token = models.CharField(max_length=64, default="", blank=True, null=True, verbose_name="API Token")
    replica_count = models.IntegerField(verbose_name="副本数量", default=1)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "机器人"
        verbose_name_plural = verbose_name
        db_table = "bot_mgmt_bot"

    @staticmethod
    def get_api_token():
        return binascii.hexlify(os.urandom(32)).decode()


class BotChannel(models.Model, EncryptMixin):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, verbose_name="机器人")
    name = models.CharField(max_length=100, verbose_name=_("name"))
    channel_type = models.CharField(max_length=100, choices=ChannelChoices.choices, verbose_name=_("channel type"))
    channel_config = YAMLField(verbose_name=_("channel config"), blank=True, null=True)
    enabled = models.BooleanField(default=False, verbose_name=_("enabled"))

    class Meta:
        db_table = "bot_mgmt_botchannel"

    def save(self, *args, **kwargs):
        if self.channel_config is None:
            super(BotChannel, self).save()
        if self.channel_type == ChannelChoices.GITLAB:
            self.encrypt_field(
                "secret_token", self.channel_config["channels.gitlab_review_channel.GitlabReviewChannel"]
            )

        elif self.channel_type == ChannelChoices.DING_TALK:
            self.encrypt_field("client_secret", self.channel_config["channels.dingtalk_channel.DingTalkChannel"])

        elif self.channel_type == ChannelChoices.ENTERPRISE_WECHAT:
            key = "channels.enterprise_wechat_channel.EnterpriseWechatChannel"
            self.encrypt_field("secret_token", self.channel_config[key])
            self.encrypt_field("aes_key", self.channel_config[key])
            self.encrypt_field("secret", self.channel_config[key])
            self.encrypt_field("token", self.channel_config[key])
        elif self.channel_type == ChannelChoices.WECHAT_OFFICIAL_ACCOUNT:
            key = "channels.wechat_official_account_channel.WechatOfficialAccountChannel"
            self.encrypt_field("aes_key", self.channel_config[key])
            self.encrypt_field("secret", self.channel_config[key])
            self.encrypt_field("token", self.channel_config[key])
        elif self.channel_type == ChannelChoices.ENTERPRISE_WECHAT_BOT:
            self.encrypt_field(
                "secret_token",
                self.channel_config["channels.enterprise_wechat_bot_channel.EnterpriseWechatBotChannel"],
            )

        super().save(*args, **kwargs)

    @cached_property
    def decrypted_channel_config(self):
        decrypted_config = self.channel_config.copy()
        if self.channel_type == ChannelChoices.GITLAB:
            self.decrypt_field("secret_token", decrypted_config["channels.gitlab_review_channel.GitlabReviewChannel"])

        if self.channel_type == ChannelChoices.DING_TALK:
            self.decrypt_field("client_secret", decrypted_config["channels.dingtalk_channel.DingTalkChannel"])

        elif self.channel_type == ChannelChoices.ENTERPRISE_WECHAT:
            key = "channels.enterprise_wechat_channel.EnterpriseWechatChannel"

            self.decrypt_field("secret_token", decrypted_config[key])
            self.decrypt_field("aes_key", decrypted_config[key])
            self.decrypt_field("secret", decrypted_config[key])
            self.decrypt_field("token", decrypted_config[key])

        elif self.channel_type == ChannelChoices.ENTERPRISE_WECHAT_BOT:
            self.decrypt_field(
                "secret_token", decrypted_config["channels.enterprise_wechat_bot_channel.EnterpriseWechatBotChannel"]
            )
        elif self.channel_type == ChannelChoices.WECHAT_OFFICIAL_ACCOUNT:
            key = "channels.wechat_official_account_channel.WechatOfficialAccountChannel"
            self.decrypt_field("secret", decrypted_config[key])
            self.decrypt_field("token", decrypted_config[key])
            self.decrypt_field("aes_key", decrypted_config[key])

        return decrypted_config

    def format_channel_config(self):
        return_data = {}
        keys = ["secret", "token", "aes_key", "client_secret"]
        for key, value in self.channel_config.items():
            return_data[key] = {i: "******" if v and i in keys else v for i, v in value.items()}
        return return_data
