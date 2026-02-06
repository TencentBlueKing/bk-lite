from django.db import models

from apps.core.mixinx import EncryptMixin
from apps.core.models.maintainer_info import MaintainerInfo


class ChannelChoices(models.TextChoices):
    EMAIL = "email", "Email"
    ENTERPRISE_WECHAT = "enterprise_wechat", "Enterprise Wechat"
    ENTERPRISE_WECHAT_BOT = "enterprise_wechat_bot", "Enterprise Wechat Bot"


class Channel(MaintainerInfo, EncryptMixin):
    name = models.CharField(max_length=100)
    channel_type = models.CharField(max_length=30, choices=ChannelChoices.choices)
    config = models.JSONField(default=dict)
    description = models.TextField()
    team = models.JSONField(default=list)
