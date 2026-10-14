from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings

COLLECT_PATH = "/rum/v1/collect"
REPLAY_PATH = "/rum/v1/replay"
SDK_PATH = "/rum/bklite-rum-sdk.js"


@dataclass(frozen=True)
class RumRuntimeSettings:
    collect_url: str
    replay_url: str
    sdk_cdn_url: str
    nats_url: str
    nats_timeout_seconds: float
    tenant_id: str
    victoria_logs_url: str
    victoria_traces_url: str
    victoria_account_id: int
    victoria_project_id: int
    victoria_timeout_seconds: float
    public_origin: str = ""


def normalize_public_origin(value: str) -> str:
    """Return scheme://host[:port] or empty when the value is not an origin."""

    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return ""
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    origin = f"{parsed.scheme}://{host}"
    if port is not None:
        origin = f"{origin}:{port}"
    return origin


def browser_endpoints(origin: str) -> dict[str, str]:
    base = normalize_public_origin(origin)
    if not base:
        return {"collect_url": "", "replay_url": "", "sdk_cdn_url": ""}
    return {
        "collect_url": f"{base}{COLLECT_PATH}",
        "replay_url": f"{base}{REPLAY_PATH}",
        "sdk_cdn_url": f"{base}{SDK_PATH}",
    }


def nats_insecure_enabled() -> bool:
    raw = getattr(settings, "RUM_NATS_INSECURE", None)
    if raw is None or raw == "":
        raw = os.getenv("RUM_NATS_INSECURE", "")
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes"}


def normalize_nats_url(value: str, *, insecure: bool) -> str:
    """生产只保留 tls:// 且不含账号口令。空值表示控制面未配置，不阻断启动。"""

    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if not parsed.hostname:
        return ""
    scheme = (parsed.scheme or "").lower()
    has_userinfo = bool(parsed.username or parsed.password)
    if scheme == "tls" and not has_userinfo:
        return raw
    if insecure and scheme == "nats":
        return raw
    return ""


def load_rum_settings() -> RumRuntimeSettings:
    configured = getattr(settings, "RUM_PUBLIC_ORIGIN", None) or os.getenv("RUM_PUBLIC_ORIGIN", "")
    public_origin = normalize_public_origin(str(configured or ""))
    endpoints = browser_endpoints(public_origin)
    nats_configured = getattr(settings, "RUM_NATS_URL", None) or os.getenv("RUM_NATS_URL", "")
    return RumRuntimeSettings(
        collect_url=endpoints["collect_url"],
        replay_url=endpoints["replay_url"],
        sdk_cdn_url=endpoints["sdk_cdn_url"],
        public_origin=public_origin,
        nats_url=normalize_nats_url(str(nats_configured or ""), insecure=nats_insecure_enabled()),
        nats_timeout_seconds=float(getattr(settings, "RUM_NATS_TIMEOUT_SECONDS", None) or os.getenv("RUM_NATS_TIMEOUT_SECONDS", "5")),
        tenant_id=getattr(settings, "RUM_TENANT_ID", None) or os.getenv("RUM_TENANT_ID", "core"),
        victoria_logs_url=getattr(settings, "RUM_VICTORIA_LOGS_URL", None) or os.getenv("RUM_VICTORIA_LOGS_URL", ""),
        victoria_traces_url=getattr(settings, "RUM_VICTORIA_TRACES_URL", None) or os.getenv("RUM_VICTORIA_TRACES_URL", ""),
        victoria_account_id=int(getattr(settings, "RUM_VICTORIA_ACCOUNT_ID", None) or os.getenv("RUM_VICTORIA_ACCOUNT_ID", "0")),
        victoria_project_id=int(getattr(settings, "RUM_VICTORIA_PROJECT_ID", None) or os.getenv("RUM_VICTORIA_PROJECT_ID", "0")),
        victoria_timeout_seconds=float(getattr(settings, "RUM_VICTORIA_TIMEOUT_SECONDS", None) or os.getenv("RUM_VICTORIA_TIMEOUT_SECONDS", "15")),
    )
