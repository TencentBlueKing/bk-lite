import binascii
import os

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models.time_info import TimeInfo


class UserAPISecret(TimeInfo):
    username = models.CharField(max_length=255)
    api_secret = models.CharField(max_length=64)
    team = models.CharField(max_length=100, default="", null=True, blank=True)

    @staticmethod
    def generate_api_secret():
        return binascii.hexlify(os.urandom(32)).decode()

    class Meta:
        unique_together = ("username", "team")


class User(AbstractUser):
    group_list = models.JSONField(default=list)
    roles = models.JSONField(default=list)
    locale = models.CharField(max_length=32, default="zh-CN")
    # rules = models.JSONField(default=dict)

    class Meta(AbstractUser.Meta):
        swappable = "AUTH_USER_MODEL"
