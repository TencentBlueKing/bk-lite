import hashlib
import hmac
import json
from typing import Any

from django.conf import settings

from apps.cmdb.constants.constants import CollectPluginTypes


class FirstCollectionPolicy:
    THRESHOLD_MINUTES = 15
    FINGERPRINT_FIELDS = (
        "instances",
        "ip_range",
        "access_point",
        "plugin_id",
        "params",
        "task_type",
        "driver_type",
        "model_id",
        "timeout",
        "is_interval",
        "cycle_value_type",
        "cycle_value",
    )

    @classmethod
    def _normalize(cls, value: Any):
        if isinstance(value, dict):
            return {str(key): cls._normalize(value[key]) for key in sorted(value, key=str)}
        if isinstance(value, (list, tuple)):
            return [cls._normalize(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _field_value(task, field):
        if field == "decrypt_credentials":
            return getattr(task, "decrypt_credentials", None)
        return getattr(task, field, None)

    @classmethod
    def _payload(cls, task):
        payload = {
            field: cls._normalize(cls._field_value(task, field))
            for field in cls.FINGERPRINT_FIELDS
        }
        payload["decrypt_credentials"] = cls._normalize(
            cls._field_value(task, "decrypt_credentials")
        )
        return payload

    @classmethod
    def is_eligible(cls, task):
        if not task or not bool(getattr(task, "is_interval", False)):
            return False
        if getattr(task, "cycle_value_type", "") != "cycle":
            return False
        if getattr(task, "task_type", "") in {
            CollectPluginTypes.K8S,
            CollectPluginTypes.CONFIG_FILE,
        }:
            return False
        try:
            cycle_minutes = int(getattr(task, "cycle_value", 0) or 0)
        except (TypeError, ValueError):
            return False
        return cycle_minutes >= cls.THRESHOLD_MINUTES

    @classmethod
    def fingerprint(cls, task):
        serialized = json.dumps(
            cls._payload(task),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            serialized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def changed_fields(cls, old_task, new_task):
        fields = (*cls.FINGERPRINT_FIELDS, "decrypt_credentials")
        return tuple(
            field
            for field in fields
            if cls._normalize(cls._field_value(old_task, field))
            != cls._normalize(cls._field_value(new_task, field))
        )

    @classmethod
    def should_trigger_update(cls, old_task, new_task):
        return cls.is_eligible(new_task) and bool(cls.changed_fields(old_task, new_task))
