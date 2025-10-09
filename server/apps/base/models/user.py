import binascii
import os

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models.time_info import TimeInfo


class UserAPISecret(TimeInfo):
    username = models.CharField(max_length=255)
    api_secret = models.CharField(max_length=64)
    team = models.IntegerField(default=0)

    @staticmethod
    def generate_api_secret():
        return binascii.hexlify(os.urandom(32)).decode()

    class Meta:
        unique_together = ("username", "team")


class User(AbstractUser):
    username_validator = UnicodeUsernameValidator()
    username = models.CharField(
        _("username"),
        max_length=150,
        unique=False,
        help_text=_("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."),
        validators=[username_validator],
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )
    group_list = models.JSONField(default=list)
    roles = models.JSONField(default=list)
    locale = models.CharField(max_length=32, default="zh-CN")
    domain = models.CharField(max_length=100, default="domain.com")
    # rules = models.JSONField(default=dict)

    class Meta(AbstractUser.Meta):
        swappable = "AUTH_USER_MODEL"
        unique_together = ("username", "domain")
