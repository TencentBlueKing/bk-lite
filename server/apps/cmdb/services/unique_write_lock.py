import hashlib
import json
import uuid
from contextlib import contextmanager
from datetime import timedelta

from django.db import IntegrityError
from django.utils.timezone import now

from apps.cmdb.models.operation import CmdbUniqueWriteLock
from apps.core.exceptions.base_app_exception import BaseAppException


class UniqueWriteLockService:
    DEFAULT_LEASE_SECONDS = 60

    @staticmethod
    def _has_value(value) -> bool:
        return value is not None and not (isinstance(value, str) and not value.strip())

    @classmethod
    def build_lock_keys(cls, model_id: str, item: dict, check_attr_map: dict) -> list[str]:
        signatures = []
        for field in check_attr_map.get("is_only", {}):
            value = item.get(field)
            if cls._has_value(value):
                signatures.append({"kind": "field", "fields": [field], "values": [value]})

        for rule in check_attr_map.get("unique_rules", []):
            values = [item.get(field) for field in rule.field_ids]
            if values and all(cls._has_value(value) for value in values):
                signatures.append({"kind": str(rule.rule_id), "fields": list(rule.field_ids), "values": values})

        keys = []
        for signature in signatures:
            raw = json.dumps(
                {"model_id": model_id, **signature}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
            )
            keys.append(hashlib.sha256(raw.encode("utf-8")).hexdigest())
        return sorted(set(keys))

    @classmethod
    def acquire(cls, lock_key: str, *, owner_token: str, lease_seconds: int | None = None) -> bool:
        current_time = now()
        lease_until = current_time + timedelta(seconds=max(1, lease_seconds or cls.DEFAULT_LEASE_SECONDS))
        try:
            _lock, created = CmdbUniqueWriteLock.objects.get_or_create(
                lock_key=lock_key,
                defaults={"owner_token": owner_token, "lease_expires_at": lease_until},
            )
        except IntegrityError:
            created = False
        if created:
            return True
        return bool(
            CmdbUniqueWriteLock.objects.filter(lock_key=lock_key, lease_expires_at__lte=current_time).update(
                owner_token=owner_token, lease_expires_at=lease_until
            )
        )

    @staticmethod
    def release(lock_key: str, *, owner_token: str) -> bool:
        deleted, _ = CmdbUniqueWriteLock.objects.filter(lock_key=lock_key, owner_token=owner_token).delete()
        return bool(deleted)

    @classmethod
    @contextmanager
    def hold(cls, lock_keys: list[str], *, lease_seconds: int | None = None):
        owner_token = uuid.uuid4().hex
        acquired = []
        try:
            for lock_key in sorted(set(lock_keys)):
                if not cls.acquire(lock_key, owner_token=owner_token, lease_seconds=lease_seconds):
                    raise BaseAppException("相同唯一键正在写入，请稍后重试")
                acquired.append(lock_key)
            yield owner_token
        finally:
            for lock_key in reversed(acquired):
                cls.release(lock_key, owner_token=owner_token)
