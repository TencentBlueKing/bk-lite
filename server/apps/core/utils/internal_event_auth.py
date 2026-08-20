import hashlib
import hmac
import json
import os
import time
from typing import Any

from django.conf import settings

AUTH_VERSION = "hmac-sha256-v1"
DEFAULT_MAX_AGE_SECONDS = 300
TRUSTED_INTERNAL_EVENT_CALLERS = frozenset({"lite-monitor", "lite-log", "lite-apm", "lite-patch"})
AUTH_PAYLOAD_FIELDS = {
    "system_mgmt.dispatch_notification": (
        "delivery_key",
        "channel_id",
        "organization_ids",
        "recipients",
        "title",
        "body",
        "event_payload",
        "required_delivery_mode",
        "producer",
        "ack_mode",
        "ack_token",
    ),
    "system_mgmt.send_msg_with_channel": (
        "channel_id",
        "title",
        "content",
        "receivers",
        "attachments",
    ),
}


def build_internal_event_payload(scope: str, values: dict[str, Any]) -> dict[str, Any]:
    """按单一字段表构造跨边界验签载荷，避免 sender/receiver 漂移。"""
    fields = AUTH_PAYLOAD_FIELDS.get(scope)
    if fields is None:
        raise ValueError("Internal event authentication scope is not registered.")
    return {field: values.get(field) for field in fields}


def _caller_key_env(caller: str, suffix: str) -> str:
    normalized_caller = caller.upper().replace("-", "_")
    return f"ALERTS_INTERNAL_EVENT_AUTH_{normalized_caller}_{suffix}"


def _auth_keys(caller: str) -> list[str]:
    keys = []
    candidates = [os.getenv(_caller_key_env(caller, "KEY"))]
    if legacy_internal_event_auth_allowed():
        candidates.extend((os.getenv("ALERTS_INTERNAL_EVENT_AUTH_KEY"), settings.SECRET_KEY))
    for key in candidates:
        if key and key not in keys:
            keys.append(key)
    return keys


def _auth_key(caller: str, key: str | None = None) -> str:
    if key:
        return key
    keys = _auth_keys(caller)
    if not keys:
        raise ValueError("Internal event authentication key is not configured.")
    return keys[0]


def _signature(scope: str, caller: str, payload: dict[str, Any], timestamp: int, key: str) -> str:
    canonical_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    message = f"{AUTH_VERSION}\n{scope}\n{caller}\n{timestamp}\n{canonical_payload}".encode()
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()


def sign_internal_event(
    scope: str,
    payload: dict[str, Any],
    caller: str,
    *,
    now: int | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    if caller not in TRUSTED_INTERNAL_EVENT_CALLERS:
        raise ValueError("Internal event caller is not trusted.")
    timestamp = int(time.time()) if now is None else int(now)
    return {
        "version": AUTH_VERSION,
        "caller": caller,
        "timestamp": timestamp,
        "signature": _signature(scope, caller, payload, timestamp, _auth_key(caller, key)),
    }


def verify_internal_event(
    scope: str,
    payload: dict[str, Any],
    auth: Any,
    caller: str,
    *,
    now: int | None = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> bool:
    if (
        caller not in TRUSTED_INTERNAL_EVENT_CALLERS
        or not isinstance(auth, dict)
        or auth.get("version") != AUTH_VERSION
        or auth.get("caller") != caller
    ):
        return False
    timestamp = auth.get("timestamp")
    signature = auth.get("signature")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int) or not isinstance(signature, str):
        return False
    current_time = int(time.time()) if now is None else int(now)
    if abs(current_time - timestamp) > max_age_seconds:
        return False

    keys = _auth_keys(caller)
    if not keys:
        return False
    previous_keys = [os.getenv(_caller_key_env(caller, "PREVIOUS_KEY"), "")]
    if legacy_internal_event_auth_allowed():
        previous_keys.append(os.getenv("ALERTS_INTERNAL_EVENT_AUTH_PREVIOUS_KEY", ""))
    keys.extend(key for key in previous_keys if key and key not in keys)
    return any(hmac.compare_digest(signature, _signature(scope, caller, payload, timestamp, key)) for key in keys)


def legacy_internal_event_auth_allowed() -> bool:
    return os.getenv("ALERTS_ALLOW_LEGACY_INTERNAL_EVENT_AUTH", "true").lower() in {
        "1",
        "true",
        "yes",
    }
