from __future__ import annotations

import os
from dataclasses import dataclass

from django.conf import settings


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


def load_rum_settings() -> RumRuntimeSettings:
    return RumRuntimeSettings(
        collect_url=getattr(settings, "RUM_COLLECT_URL", None) or os.getenv("RUM_COLLECT_URL", "http://127.0.0.1:4319/rum/v1/collect"),
        replay_url=getattr(settings, "RUM_REPLAY_URL", None) or os.getenv("RUM_REPLAY_URL", "http://127.0.0.1:4320/rum/v1/replay"),
        sdk_cdn_url=getattr(settings, "RUM_SDK_CDN_URL", None) or os.getenv("RUM_SDK_CDN_URL", "http://127.0.0.1:3000/rum/bklite-rum-sdk.js"),
        nats_url=getattr(settings, "RUM_NATS_URL", None) or os.getenv("RUM_NATS_URL", ""),
        nats_timeout_seconds=float(getattr(settings, "RUM_NATS_TIMEOUT_SECONDS", None) or os.getenv("RUM_NATS_TIMEOUT_SECONDS", "5")),
        tenant_id=getattr(settings, "RUM_TENANT_ID", None) or os.getenv("RUM_TENANT_ID", "core"),
        victoria_logs_url=getattr(settings, "RUM_VICTORIA_LOGS_URL", None) or os.getenv("RUM_VICTORIA_LOGS_URL", ""),
        victoria_traces_url=getattr(settings, "RUM_VICTORIA_TRACES_URL", None) or os.getenv("RUM_VICTORIA_TRACES_URL", ""),
        victoria_account_id=int(getattr(settings, "RUM_VICTORIA_ACCOUNT_ID", None) or os.getenv("RUM_VICTORIA_ACCOUNT_ID", "0")),
        victoria_project_id=int(getattr(settings, "RUM_VICTORIA_PROJECT_ID", None) or os.getenv("RUM_VICTORIA_PROJECT_ID", "0")),
        victoria_timeout_seconds=float(getattr(settings, "RUM_VICTORIA_TIMEOUT_SECONDS", None) or os.getenv("RUM_VICTORIA_TIMEOUT_SECONDS", "15")),
    )
