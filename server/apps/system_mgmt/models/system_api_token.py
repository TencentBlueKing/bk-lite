import binascii
import hashlib
import os

from django.db import models
from django.db.models import Q
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

    @classmethod
    def find_live_by_secret(cls, secret: str):
        if not secret or cls.is_hashed(secret):
            return None
        live = Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        return cls._default_manager.filter(
            live,
            secret_hash=cls.hash_secret(secret),
            enabled=True,
        ).first()

    def get_secret_preview(self) -> str:
        return "bksys_********" if self.secret_hash else ""
