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
    nats_user: str = ""
    nats_password: str = ""
    nats_tls_ca_file: str = ""


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


def _setting_or_env(name: str) -> str:
    raw = getattr(settings, name, None)
    if raw is None or raw == "":
        raw = os.getenv(name, "")
    return str(raw or "")


def platform_nats_endpoint(value: str) -> str:
    """取平台 NATS_SERVERS 的主机，丢掉其中的账号口令。无协议时按 nats://。"""

    raw = (value or "").strip()
    if not raw:
        return ""
    has_scheme = "://" in raw
    try:
        parsed = urlsplit(raw if has_scheme else f"//{raw}")
        port = parsed.port
    except ValueError:
        return ""
    scheme = (parsed.scheme or "").lower()
    if not parsed.hostname or port is None:
        return ""
    if has_scheme and scheme not in {"nats", "tls"}:
        return ""
    if not has_scheme:
        scheme = "nats"
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return ""
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    return f"{scheme}://{host}:{port}"


def normalize_nats_endpoint(url: str, user: str, password: str) -> tuple[str, str, str]:
    """地址只保留 nats:// 或 tls:// 的主机。账号口令另给，写进 URL 或只给一半都视为未配置。"""

    raw = (url or "").strip()
    identity = (user or "").strip()
    secret = password or ""
    if not raw:
        return "", "", ""
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return "", "", ""
    scheme = (parsed.scheme or "").lower()
    if (
        parsed.username
        or parsed.password
        or not parsed.hostname
        or scheme not in {"nats", "tls"}
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return "", "", ""
    if bool(identity) != bool(secret):
        return "", "", ""
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    endpoint = f"{scheme}://{host}"
    if port is not None:
        endpoint = f"{endpoint}:{port}"
    return endpoint, identity, secret


def load_rum_settings() -> RumRuntimeSettings:
    configured = getattr(settings, "RUM_PUBLIC_ORIGIN", None) or os.getenv("RUM_PUBLIC_ORIGIN", "")
    public_origin = normalize_public_origin(str(configured or ""))
    endpoints = browser_endpoints(public_origin)
    nats_url, nats_user, nats_password = normalize_nats_endpoint(
        platform_nats_endpoint(_setting_or_env("NATS_SERVERS")),
        _setting_or_env("RUM_NATS_USER"),
        _setting_or_env("RUM_NATS_PASSWORD"),
    )
    tls_ca_file = _setting_or_env("NATS_TLS_CA_FILE").strip() if nats_url.startswith("tls://") else ""
    return RumRuntimeSettings(
        collect_url=endpoints["collect_url"],
        replay_url=endpoints["replay_url"],
        sdk_cdn_url=endpoints["sdk_cdn_url"],
        public_origin=public_origin,
        nats_url=nats_url,
        nats_user=nats_user,
        nats_password=nats_password,
        nats_tls_ca_file=tls_ca_file,
        nats_timeout_seconds=float(getattr(settings, "RUM_NATS_TIMEOUT_SECONDS", None) or os.getenv("RUM_NATS_TIMEOUT_SECONDS", "5")),
        tenant_id=getattr(settings, "RUM_TENANT_ID", None) or os.getenv("RUM_TENANT_ID", "core"),
        victoria_logs_url=getattr(settings, "RUM_VICTORIA_LOGS_URL", None) or os.getenv("RUM_VICTORIA_LOGS_URL", ""),
        victoria_traces_url=getattr(settings, "RUM_VICTORIA_TRACES_URL", None) or os.getenv("RUM_VICTORIA_TRACES_URL", ""),
        victoria_account_id=int(getattr(settings, "RUM_VICTORIA_ACCOUNT_ID", None) or os.getenv("RUM_VICTORIA_ACCOUNT_ID", "0")),
        victoria_project_id=int(getattr(settings, "RUM_VICTORIA_PROJECT_ID", None) or os.getenv("RUM_VICTORIA_PROJECT_ID", "0")),
        victoria_timeout_seconds=float(getattr(settings, "RUM_VICTORIA_TIMEOUT_SECONDS", None) or os.getenv("RUM_VICTORIA_TIMEOUT_SECONDS", "15")),
    )
