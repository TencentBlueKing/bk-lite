from __future__ import annotations

import re
import secrets
from urllib.parse import urlparse

from apps.rum.constants import MAX_ORIGINS

APPLICATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
BROWSER_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{16,256}$")


class ValidationError(ValueError):
    """Operator-facing invalid input (maps to HTTP 400)."""


def valid_application(name: str) -> bool:
    return bool(APPLICATION_RE.match((name or "").strip()))


def valid_browser_key(key: str) -> bool:
    return bool(BROWSER_KEY_RE.match((key or "").strip()))


def valid_budgets(budget: dict) -> bool:
    try:
        return all(
            int(budget[key]) > 0
            for key in (
                "requestsPerMinute",
                "compressedBytesPerMinute",
                "decompressedBytesPerMinute",
                "eventsPerMinute",
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def new_browser_key() -> str:
    return secrets.token_urlsafe(32).rstrip("=")


def canonical_origin(value: str) -> str:
    value = (value or "").strip()
    if not value or value in {"null", "*"} or any(ch in value for ch in "*\\"):
        raise ValidationError("origin must be an exact canonical HTTP or HTTPS origin")
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValidationError("origin must be an exact canonical HTTP or HTTPS origin")
    host = parsed.hostname.lower()
    if parsed.port is not None:
        if ":" in host:
            host = f"[{host}]:{parsed.port}"
        else:
            host = f"{host}:{parsed.port}"
    elif ":" in host:
        host = f"[{host}]"
    return f"{parsed.scheme}://{host}"


def canonical_origins(origins: list[str] | None) -> list[str]:
    if not origins:
        raise ValidationError("at least one allowed origin is required")
    if len(origins) > MAX_ORIGINS:
        raise ValidationError(f"at most {MAX_ORIGINS} allowed origins are supported")
    seen: set[str] = set()
    out: list[str] = []
    for origin in origins:
        canonical = canonical_origin(origin)
        if canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    return out
