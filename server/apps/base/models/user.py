import binascii
import hashlib
import os

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models.time_info import TimeInfo


class UserAPISecret(TimeInfo):
    HASH_PREFIX = "sha256$"

    username = models.CharField(max_length=255)
    domain = models.CharField(max_length=255, default="domain.com")
    api_secret = models.CharField(max_length=80)
    team = models.IntegerField(default=0)

    @staticmethod
    def generate_api_secret():
        return binascii.hexlify(os.urandom(32)).decode()

    @classmethod
    def hash_api_secret(cls, api_secret: str) -> str:
        if not api_secret:
            return api_secret
        if cls.is_hashed_api_secret(api_secret):
            return api_secret
        return f"{cls.HASH_PREFIX}{hashlib.sha256(api_secret.encode()).hexdigest()}"

    @classmethod
    def is_hashed_api_secret(cls, api_secret: str) -> bool:
        return bool(api_secret and api_secret.startswith(cls.HASH_PREFIX))

    @classmethod
    def find_by_api_secret(cls, api_secret: str):
        if not api_secret:
            return None
        if cls.is_hashed_api_secret(api_secret):
            return None

        hashed_secret = cls.hash_api_secret(api_secret)
        user_secret = cls._default_manager.filter(api_secret=hashed_secret).first()
        if user_secret:
            return user_secret

        # 滚动发布兼容：迁移尚未执行到的旧明文记录仍可认证。
        return cls._default_manager.filter(api_secret=api_secret).first()

    def get_api_secret_preview(self) -> str:
        return "********" if self.api_secret else ""

    class Meta:
        unique_together = ("username", "domain", "team")


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
