import hashlib
import hmac
import json
import os
import time
from typing import Any

from django.conf import settings

AUTH_VERSION = "hmac-sha256-v1"
DEFAULT_MAX_AGE_SECONDS = 300


def _auth_key(key: str | None = None) -> str:
    return key or os.getenv("ALERTS_INTERNAL_EVENT_AUTH_KEY") or settings.SECRET_KEY


def _signature(scope: str, payload: dict[str, Any], timestamp: int, key: str) -> str:
    canonical_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    message = f"{AUTH_VERSION}\n{scope}\n{timestamp}\n{canonical_payload}".encode()
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()


def sign_internal_event(
    scope: str,
    payload: dict[str, Any],
    *,
    now: int | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    timestamp = int(time.time()) if now is None else int(now)
    return {
        "version": AUTH_VERSION,
        "timestamp": timestamp,
        "signature": _signature(scope, payload, timestamp, _auth_key(key)),
    }


def verify_internal_event(
    scope: str,
    payload: dict[str, Any],
    auth: Any,
    *,
    now: int | None = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> bool:
    if not isinstance(auth, dict) or auth.get("version") != AUTH_VERSION:
        return False
    timestamp = auth.get("timestamp")
    signature = auth.get("signature")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int) or not isinstance(signature, str):
        return False
    current_time = int(time.time()) if now is None else int(now)
    if abs(current_time - timestamp) > max_age_seconds:
        return False

    keys = [_auth_key()]
    previous_key = os.getenv("ALERTS_INTERNAL_EVENT_AUTH_PREVIOUS_KEY", "")
    if previous_key and previous_key not in keys:
        keys.append(previous_key)
    return any(hmac.compare_digest(signature, _signature(scope, payload, timestamp, key)) for key in keys)


def legacy_internal_event_auth_allowed() -> bool:
    return os.getenv("ALERTS_ALLOW_LEGACY_INTERNAL_EVENT_AUTH", "false").lower() in {
        "1",
        "true",
        "yes",
    }
