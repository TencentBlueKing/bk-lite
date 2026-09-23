from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Protocol

from django.conf import settings

from apps.core.logger import rum_logger as logger


class ReplayIndex(Protocol):
    def available(self) -> bool:
        ...

    def has_ready(self, application: str, session_id: str) -> bool:
        ...

    def replay_manifest(self, tenant_id: str, application: str, session_id: str) -> dict:
        ...


class UnavailableReplayIndex:
    def available(self) -> bool:
        return False

    def has_ready(self, application: str, session_id: str) -> bool:
        return False

    def replay_manifest(self, tenant_id: str, application: str, session_id: str) -> dict:
        return {"state": "unavailable", "retentionDays": 0, "recordings": []}


class MemoryReplayIndex:
    """Test double with in-memory manifests."""

    def __init__(self):
        self._ready: set[tuple[str, str]] = set()
        self._manifests: dict[tuple[str, str], dict] = {}
        self._blobs: dict[str, bytes] = {}

    def available(self) -> bool:
        return True

    def mark_ready(self, application: str, session_id: str, manifest: dict | None = None) -> None:
        key = (application, session_id)
        self._ready.add(key)
        self._manifests[key] = manifest or {
            "state": "ready",
            "retentionDays": 30,
            "recordings": [
                {
                    "recordingId": "rec-1",
                    "pageId": "page-1",
                    "segments": [
                        {
                            "sequence": 0,
                            "startedAt": "2026-01-01T00:00:00Z",
                            "endedAt": "2026-01-01T00:00:01Z",
                            "eventCount": 10,
                            "compressedBytes": 100,
                            "uncompressedBytes": 200,
                            "hasFullSnapshot": True,
                            "objectKey": f"{application}/{session_id}/0.rrweb",
                            "ref": "",
                        }
                    ],
                }
            ],
        }

    def put_blob(self, object_key: str, blob: bytes) -> None:
        self._blobs[object_key] = blob

    def has_ready(self, application: str, session_id: str) -> bool:
        return (application, session_id) in self._ready

    def replay_manifest(self, tenant_id: str, application: str, session_id: str) -> dict:
        return json.loads(
            json.dumps(
                self._manifests.get((application, session_id))
                or {
                    "state": "missing",
                    "retentionDays": 30,
                    "recordings": [],
                }
            )
        )

    def segment_blob(self, object_key: str) -> bytes | None:
        return self._blobs.get(object_key)


def _signing_secret() -> bytes:
    value = (getattr(settings, "RUM_REPLAY_SIGNING_SECRET", None) or os.getenv("RUM_REPLAY_SIGNING_SECRET", "")).strip()
    if not value:
        return b""
    return value.encode("utf-8")


def sign_payload(kind: str, claims: dict) -> str:
    secret = _signing_secret()
    if not secret:
        raise RuntimeError("replay signing secret is not configured")
    body = {"kind": kind, **claims}
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    digest = hmac.new(secret, raw, hashlib.sha256).digest()
    packed = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    mac = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{packed}.{mac}"


def verify_payload(token: str, kind: str) -> dict | None:
    secret = _signing_secret()
    if not secret or not token or "." not in token:
        return None
    packed, mac = token.rsplit(".", 1)
    try:
        raw = base64.urlsafe_b64decode(packed + "=" * (-len(packed) % 4))
        digest = base64.urlsafe_b64decode(mac + "=" * (-len(mac) % 4))
    except (ValueError, TypeError):
        return None
    expected = hmac.new(secret, raw, hashlib.sha256).digest()
    if not hmac.compare_digest(digest, expected):
        return None
    try:
        body = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    if body.get("kind") != kind:
        return None
    expires = body.get("expiresAtMs")
    if expires is not None and int(expires) < int(time.time() * 1000):
        return None
    return body


def build_replay_index_from_settings():
    """Assemble Redis/MinIO-backed index when env is present; otherwise degrade."""
    from apps.rum.services.replay_store import RedisReplayIndex, connect_minio_store, connect_redis

    url = (
        getattr(settings, "RUM_REPLAY_INDEX_REDIS_URL", None)
        or os.getenv("RUM_REPLAY_INDEX_REDIS_URL", "")
        or getattr(settings, "RUM_REPLAY_REDIS_URL", None)
        or os.getenv("RUM_REPLAY_REDIS_URL", "")
    ).strip()
    if not url:
        return UnavailableReplayIndex()
    try:
        client = connect_redis(url)
        client.ping()
        return RedisReplayIndex(client, object_store=connect_minio_store())
    except Exception as exc:
        logger.warning(
            "rum replay index unavailable failed_stage=connect error_type=%s",
            type(exc).__name__,
        )
        return UnavailableReplayIndex()


_replay_index: ReplayIndex | None = None


def get_replay_index() -> ReplayIndex:
    global _replay_index
    if _replay_index is None:
        _replay_index = build_replay_index_from_settings()
    return _replay_index


def set_replay_index(index: ReplayIndex | None) -> None:
    global _replay_index
    _replay_index = index
