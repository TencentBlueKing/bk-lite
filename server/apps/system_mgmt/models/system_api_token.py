import binascii
import hashlib
import os

from django.db import models
from django.utils import timezone

from apps.core.models.time_info import TimeInfo


class SystemAPIToken(TimeInfo):
    PREFIX = "bksys_"
    HASH_PREFIX = "sha256$"

    system_id = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=128, default="")
    secret_hash = models.CharField(max_length=80, db_index=True)
    scope = models.JSONField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=32, default="")
    created_by_domain = models.CharField(max_length=100, default="domain.com")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("system_id", "name"),
                name="uniq_systemapitoken_system_id_name",
            ),
        ]

    @classmethod
    def generate_secret(cls) -> str:
        return f"{cls.PREFIX}{binascii.hexlify(os.urandom(32)).decode()}"

    @classmethod
    def hash_secret(cls, secret: str) -> str:
        if not secret:
            return secret
        if cls.is_hashed(secret):
            return secret
        return f"{cls.HASH_PREFIX}{hashlib.sha256(secret.encode()).hexdigest()}"

    @classmethod
    def is_hashed(cls, secret: str) -> bool:
        return bool(secret and secret.startswith(cls.HASH_PREFIX))

    def is_live(self) -> bool:
        if not self.enabled:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()

    @classmethod
    def find_by_secret_including_disabled(cls, secret: str):
        """按哈希查钥匙行，含过期与已禁用。仅供网关审计身份，不放宽认证。"""
        if not secret or cls.is_hashed(secret):
            return None
        return cls._default_manager.filter(secret_hash=cls.hash_secret(secret)).first()

    @classmethod
    def find_live_by_secret(cls, secret: str):
        row = cls.find_by_secret_including_disabled(secret)
        if row is None or not row.is_live():
            return None
        return row

    def get_secret_preview(self) -> str:
        return "bksys_********" if self.secret_hash else ""
