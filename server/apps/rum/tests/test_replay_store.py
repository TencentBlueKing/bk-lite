"""Redis/MinIO replay index — behavior at the ReplayIndex seam."""

from __future__ import annotations

import io
import json
import logging

from django.test import override_settings

from apps.rum.services.replay import UnavailableReplayIndex, build_replay_index_from_settings, get_replay_index, set_replay_index


class FakeRedis:
    def __init__(self):
        self.kv: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.ping_ok = True

    def ping(self):
        if not self.ping_ok:
            raise ConnectionError("redis down")
        return True

    def get(self, key: str):
        return self.kv.get(key)

    def smembers(self, key: str):
        return set(self.sets.get(key, set()))

    def mget(self, keys):
        return [self.kv.get(k) for k in keys]

    def seed_ready(self, *, application: str, session_key: str, faro_session_id: str, recording_id: str = "rec-1"):
        object_key = f"v1/{application}/{session_key}/{recording_id}/0.json.gz"
        slot = f"ops:rum:v2:replay:idx:{application}:{session_key}:{recording_id}:0"
        row = {
            "tenant_id": "core",
            "Application": application,
            "SessionId": faro_session_id,
            "SessionKey": session_key,
            "PageId": "page-1",
            "RecordingId": recording_id,
            "SegmentId": "seg-1",
            "Sequence": 0,
            "StartTime": "2026-09-22T03:00:00Z",
            "EndTime": "2026-09-22T03:00:01Z",
            "EventCount": 2,
            "CompressedBytes": 440,
            "UncompressedBytes": 900,
            "HasFullSnapshot": 1,
            "ChecksumSHA256": "a" * 64,
            "ObjectKey": object_key,
            "Status": "ready",
        }
        self.kv[slot] = json.dumps(row)
        self.sets.setdefault(f"ops:rum:v2:replay:sess:{application}:{session_key}", set()).add(slot)
        return object_key, row


class FakeObjectStore:
    def __init__(self):
        self.blobs: dict[str, bytes] = {}

    def get_bytes(self, object_key: str) -> bytes | None:
        return self.blobs.get(object_key)


def test_unavailable_when_redis_url_missing(monkeypatch):
    set_replay_index(None)
    monkeypatch.delenv("RUM_REPLAY_INDEX_REDIS_URL", raising=False)
    monkeypatch.delenv("RUM_REPLAY_REDIS_URL", raising=False)
    index = build_replay_index_from_settings()
    assert isinstance(index, UnavailableReplayIndex)
    assert index.available() is False


def test_has_ready_and_manifest_from_redis_session_key():
    from apps.rum.services.replay_store import RedisReplayIndex

    redis = FakeRedis()
    object_key, _ = redis.seed_ready(
        application="local-demo",
        session_key="d334781a5de70001265c68b0f5e7b082",
        faro_session_id="faro-sess-1",
    )
    store = FakeObjectStore()
    store.blobs[object_key] = b"\x1f\x8bgz"
    index = RedisReplayIndex(redis, object_store=store)

    assert index.available() is True
    assert index.has_ready("local-demo", "d334781a5de70001265c68b0f5e7b082") is True
    # Faro session id alone must not miss when SessionId is indexed via product key only —
    # product path looks up by the same id the sessions list exposes (session key preferred).
    assert index.has_ready("local-demo", "faro-sess-1") is False

    manifest = index.replay_manifest("core", "local-demo", "d334781a5de70001265c68b0f5e7b082")
    assert manifest["state"] == "ready"
    assert manifest["retentionDays"] == 14
    assert len(manifest["recordings"]) == 1
    seg = manifest["recordings"][0]["segments"][0]
    assert seg["sequence"] == 0
    assert seg["objectKey"] == object_key
    assert seg["hasFullSnapshot"] is True
    assert index.segment_blob(object_key) == b"\x1f\x8bgz"


def test_manifest_not_recorded_when_session_missing():
    from apps.rum.services.replay_store import RedisReplayIndex

    index = RedisReplayIndex(FakeRedis(), object_store=FakeObjectStore())
    manifest = index.replay_manifest("core", "local-demo", "missing")
    assert manifest["state"] == "not-recorded"
    assert manifest["recordings"] == []


def test_replay_bucket_is_registered_with_platform_minio():
    from django.conf import settings

    assert "rum-replay" in settings.MINIO_PRIVATE_BUCKETS


@override_settings(
    MINIO_ENDPOINT="minio.internal:9000",
    MINIO_ACCESS_KEY="platform-access",
    MINIO_SECRET_KEY="platform-secret",
    MINIO_USE_HTTPS=False,
    MINIO_PRIVATE_BUCKETS=["rum-replay"],
    MINIO_PUBLIC_BUCKETS=[],
)
def test_connect_minio_store_uses_platform_credentials(monkeypatch):
    from apps.rum.services.replay_store import MinioObjectStore, connect_minio_store

    monkeypatch.setenv("RUM_MINIO_ENDPOINT", "127.0.0.1:19000")
    monkeypatch.setenv("RUM_MINIO_ACCESS_KEY", "rum-only-key")
    monkeypatch.setenv("RUM_MINIO_SECRET_KEY", "rum-only-secret")
    store = connect_minio_store()

    assert isinstance(store, MinioObjectStore)
    backend = store._storage
    assert backend.bucket == "rum-replay"
    assert backend._MinioBackend__MINIO_ENDPOINT == "minio.internal:9000"
    assert backend._MinioBackend__MINIO_ACCESS_KEY == "platform-access"
    assert backend._MinioBackend__MINIO_SECRET_KEY == "platform-secret"
    assert "rum-only-key" not in {
        backend._MinioBackend__MINIO_ENDPOINT,
        backend._MinioBackend__MINIO_ACCESS_KEY,
        backend._MinioBackend__MINIO_SECRET_KEY,
    }


@override_settings(
    MINIO_ENDPOINT="minio.internal:9000",
    MINIO_ACCESS_KEY="",
    MINIO_SECRET_KEY="",
)
def test_connect_minio_store_without_platform_credentials_is_null(monkeypatch):
    from apps.rum.services.replay_store import NullObjectStore, connect_minio_store

    monkeypatch.setenv("RUM_MINIO_ENDPOINT", "127.0.0.1:19000")
    monkeypatch.setenv("RUM_MINIO_ACCESS_KEY", "rum-only-key")
    monkeypatch.setenv("RUM_MINIO_SECRET_KEY", "rum-only-secret")
    assert isinstance(connect_minio_store(), NullObjectStore)


def test_minio_object_store_reads_open_and_hides_failures(caplog):
    from apps.rum.services.replay_store import MinioObjectStore

    class Storage:
        def open(self, name, mode="rb"):
            assert mode == "rb"
            if name == "missing":
                raise RuntimeError("secret-object-body")
            return io.BytesIO(b"segment")

    store = MinioObjectStore(Storage())
    assert store.get_bytes("  ") is None
    assert store.get_bytes("v1/app/sess/0.json.gz") == b"segment"
    with caplog.at_level(logging.DEBUG, logger="rum"):
        assert store.get_bytes("missing") is None
    assert "RuntimeError" in caplog.text
    assert "secret-object-body" not in caplog.text


def test_get_replay_index_caches_built_instance(monkeypatch):
    set_replay_index(None)
    monkeypatch.setenv("RUM_REPLAY_INDEX_REDIS_URL", "redis://example.invalid:1/0")
    # Force unavailable on connect failure rather than hanging.
    monkeypatch.setattr(
        "apps.rum.services.replay_store.connect_redis",
        lambda url: (_ for _ in ()).throw(ConnectionError("boom")),
    )
    first = get_replay_index()
    second = get_replay_index()
    assert first is second
    assert first.available() is False
