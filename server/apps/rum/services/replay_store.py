"""Redis index + MinIO object store for RUM session replay."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol
from urllib.parse import urlparse

import redis
from minio import Minio

from apps.core.logger import rum_logger as logger

READY = "ready"
PENDING = "pending"
TOMBSTONE = "tombstone"
RETENTION_DAYS = 14


class ObjectStore(Protocol):
    def get_bytes(self, object_key: str) -> bytes | None:
        ...


class NullObjectStore:
    def get_bytes(self, object_key: str) -> bytes | None:
        return None


class MinioObjectStore:
    def __init__(self, client: Minio, bucket: str):
        self._client = client
        self._bucket = bucket

    def get_bytes(self, object_key: str) -> bytes | None:
        key = (object_key or "").strip()
        if not key:
            return None
        try:
            response = self._client.get_object(self._bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:
            logger.debug(
                "rum replay object get failed object_key=%s error_type=%s",
                key[:120],
                type(exc).__name__,
            )
            return None


def connect_redis(url: str):
    return redis.Redis.from_url(url, decode_responses=True)


def connect_minio_store() -> ObjectStore:
    endpoint = (os.getenv("RUM_MINIO_ENDPOINT") or "").strip()
    access = (os.getenv("RUM_MINIO_ACCESS_KEY") or "").strip()
    secret = (os.getenv("RUM_MINIO_SECRET_KEY") or "").strip()
    bucket = (os.getenv("RUM_MINIO_BUCKET") or "rum-replay").strip() or "rum-replay"
    if not endpoint or not access or not secret:
        return NullObjectStore()
    secure = (os.getenv("RUM_MINIO_SECURE") or "false").strip().lower() in {"1", "true", "yes"}
    host = endpoint
    # Minio client wants host[:port] without scheme.
    if "://" in endpoint:
        parsed = urlparse(endpoint)
        host = parsed.netloc or parsed.path
        if parsed.scheme == "https":
            secure = True
    client = Minio(host, access_key=access, secret_key=secret, secure=secure)
    return MinioObjectStore(client, bucket)


def session_set_key(application: str, session_id: str) -> str:
    return f"ops:rum:v2:replay:sess:{application}:{session_id}"


class RedisReplayIndex:
    """Product read path over the collector's Redis replay index contract."""

    def __init__(self, client, object_store: ObjectStore | None = None):
        self._client = client
        self._objects = object_store or NullObjectStore()

    def available(self) -> bool:
        return True

    def has_ready(self, application: str, session_id: str) -> bool:
        rows = self._rows(application, session_id)
        return any((row.get("Status") or "") == READY for row in rows)

    def replay_manifest(self, tenant_id: str, application: str, session_id: str) -> dict:
        del tenant_id  # tenant is enforced at admission write-time; index rows are app-scoped.
        rows = self._rows(application, session_id)
        usable = [row for row in rows if (row.get("Status") or "") in {READY, PENDING}]
        if not usable:
            return {"state": "not-recorded", "retentionDays": RETENTION_DAYS, "recordings": []}
        ready_rows = [row for row in usable if row.get("Status") == READY]
        state = "ready" if ready_rows else "pending"
        source = ready_rows or usable
        recordings: dict[str, dict[str, Any]] = {}
        for row in source:
            recording_id = (row.get("RecordingId") or "").strip() or "recording"
            page_id = (row.get("PageId") or "").strip() or recording_id
            bucket = recordings.setdefault(
                recording_id,
                {"recordingId": recording_id, "pageId": page_id, "segments": []},
            )
            bucket["segments"].append(
                {
                    "sequence": int(row.get("Sequence") or 0),
                    "startedAt": row.get("StartTime") or "",
                    "endedAt": row.get("EndTime") or "",
                    "eventCount": int(row.get("EventCount") or 0),
                    "compressedBytes": int(row.get("CompressedBytes") or 0),
                    "uncompressedBytes": int(row.get("UncompressedBytes") or 0),
                    "hasFullSnapshot": bool(int(row.get("HasFullSnapshot") or 0)),
                    "objectKey": row.get("ObjectKey") or "",
                    "ref": "",
                }
            )
        out = []
        for recording in recordings.values():
            recording["segments"].sort(key=lambda item: item["sequence"])
            out.append(recording)
        out.sort(key=lambda item: item["recordingId"])
        return {"state": state, "retentionDays": RETENTION_DAYS, "recordings": out}

    def segment_blob(self, object_key: str) -> bytes | None:
        return self._objects.get_bytes(object_key)

    def _rows(self, application: str, session_id: str) -> list[dict]:
        application = (application or "").strip()
        session_id = (session_id or "").strip()
        if not application or not session_id:
            return []
        try:
            keys = list(self._client.smembers(session_set_key(application, session_id)))
        except Exception as exc:
            logger.warning(
                "rum replay index smembers failed application=%s error_type=%s",
                application,
                type(exc).__name__,
            )
            return []
        if not keys:
            return []
        try:
            values = self._client.mget(keys)
        except Exception as exc:
            logger.warning(
                "rum replay index mget failed application=%s error_type=%s",
                application,
                type(exc).__name__,
            )
            return []
        rows: list[dict] = []
        for raw in values or []:
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows
