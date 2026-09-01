"""配置快照轮次元数据：有界协议、幂等 Redis 存储与精确读取。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

ROUND_METADATA_SCHEMA_VERSION = 1
ROUND_METADATA_KIND = "inventory_snapshot"
ROUND_METADATA_TTL_SECONDS = 24 * 60 * 60
MAX_ROUND_METADATA_BYTES = 16 * 1024
MAX_ROUND_METADATA_LOOKUPS = 50
MAX_ROUND_METADATA_RESPONSE_BYTES = 1024 * 1024
MAX_IDENTITY_LENGTH = 512
ROUND_METADATA_KEY_PREFIX = "stargazer:collection:v1:round-meta"
SUPPORTED_MODELS = frozenset({"pc", "winsphere"})


class RoundMetadataError(RuntimeError):
    error_code = "metadata_unavailable"

    def __init__(self, error_code: str | None = None) -> None:
        super().__init__(error_code or self.error_code)
        self.error_code = error_code or self.error_code


class RoundMetadataValidationError(RoundMetadataError, ValueError):
    error_code = "invalid_request"


class RoundMetadataConflictError(RoundMetadataError):
    error_code = "metadata_conflict"


class RoundMetadataMissingError(RoundMetadataError):
    error_code = "metadata_missing"


def _bounded_string(value, field: str, *, allow_empty: bool = False) -> str:
    result = str(value or "").strip()
    if (not result and not allow_empty) or len(result) > MAX_IDENTITY_LENGTH:
        raise RoundMetadataValidationError("invalid_request")
    return result


def _timestamp(value) -> int:
    if isinstance(value, bool):
        raise RoundMetadataValidationError("invalid_request")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise RoundMetadataValidationError("invalid_request") from exc
    if result <= 0:
        raise RoundMetadataValidationError("invalid_request")
    return result


def canonical_json(payload: Mapping) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise RoundMetadataValidationError("invalid_request") from exc


def _non_negative_integer(value) -> int:
    if type(value) is not int or value < 0:
        raise RoundMetadataValidationError("invalid_request")
    return value


def _validate_details(model_id: str, details: Mapping) -> dict:
    normalized = dict(details)
    if model_id == "pc":
        if set(normalized) != {"software_expected_count", "software_error_count"}:
            raise RoundMetadataValidationError("invalid_request")
        normalized["software_expected_count"] = _non_negative_integer(normalized["software_expected_count"])
        normalized["software_error_count"] = _non_negative_integer(normalized["software_error_count"])
    elif model_id == "winsphere":
        if set(normalized) != {"snapshot_manifest"} or not isinstance(normalized["snapshot_manifest"], Mapping):
            raise RoundMetadataValidationError("invalid_request")
        normalized["snapshot_manifest"] = dict(normalized["snapshot_manifest"])
    return normalized


def validate_round_metadata_envelope(envelope: Mapping) -> dict:
    if not isinstance(envelope, Mapping):
        raise RoundMetadataValidationError("invalid_request")
    model_id = _bounded_string(envelope.get("model_id"), "model_id")
    if model_id not in SUPPORTED_MODELS:
        raise RoundMetadataValidationError("invalid_request")
    task_id = _bounded_string(envelope.get("collection_task_id"), "collection_task_id")
    instance_id = _bounded_string(envelope.get("instance_id"), "instance_id")
    if instance_id != f"cmdb_{task_id}":
        raise RoundMetadataValidationError("invalid_request")
    snapshot_status = _bounded_string(envelope.get("snapshot_status"), "snapshot_status")
    if snapshot_status not in {"complete", "partial"}:
        raise RoundMetadataValidationError("invalid_request")
    details = envelope.get("details") or {}
    if not isinstance(details, Mapping):
        raise RoundMetadataValidationError("invalid_request")
    normalized = {
        "schema_version": envelope.get("schema_version"),
        "kind": envelope.get("kind"),
        "collection_task_id": task_id,
        "instance_id": instance_id,
        "collection_target": _bounded_string(envelope.get("collection_target"), "collection_target"),
        "collection_plugin_ref": _bounded_string(envelope.get("collection_plugin_ref"), "collection_plugin_ref"),
        "model_id": model_id,
        "publish_timestamp_ms": _timestamp(envelope.get("publish_timestamp_ms")),
        "snapshot_id": _bounded_string(envelope.get("snapshot_id"), "snapshot_id"),
        "snapshot_status": snapshot_status,
        "details": _validate_details(model_id, details),
    }
    if normalized["schema_version"] != ROUND_METADATA_SCHEMA_VERSION or normalized["kind"] != ROUND_METADATA_KIND:
        raise RoundMetadataValidationError("invalid_request")
    encoded = canonical_json(normalized).encode("utf-8")
    if len(encoded) > MAX_ROUND_METADATA_BYTES:
        raise RoundMetadataValidationError("metadata_too_large")
    return normalized


def build_round_metadata_envelope(*, task_id, target, plugin_ref, model_id, publish_timestamp_ms, metadata) -> dict:
    if not isinstance(metadata, Mapping):
        raise RoundMetadataValidationError("invalid_request")
    return validate_round_metadata_envelope(
        {
            "schema_version": ROUND_METADATA_SCHEMA_VERSION,
            "kind": ROUND_METADATA_KIND,
            "collection_task_id": str(task_id),
            "instance_id": f"cmdb_{task_id}",
            "collection_target": target,
            "collection_plugin_ref": plugin_ref,
            "model_id": model_id,
            "publish_timestamp_ms": publish_timestamp_ms,
            "snapshot_id": metadata.get("snapshot_id"),
            "snapshot_status": metadata.get("snapshot_status"),
            "details": metadata.get("details") or {},
        }
    )


def round_metadata_key(task_id, target, publish_timestamp_ms) -> str:
    task = _bounded_string(task_id, "collection_task_id")
    normalized_target = _bounded_string(target, "collection_target")
    timestamp = _timestamp(publish_timestamp_ms)
    target_hash = hashlib.sha256(normalized_target.encode("utf-8")).hexdigest()
    return f"{ROUND_METADATA_KEY_PREFIX}:{task}:{target_hash}:{timestamp}"


def validate_lookups(lookups: Sequence[Mapping]) -> list[dict]:
    if isinstance(lookups, (str, bytes)) or not isinstance(lookups, Sequence):
        raise RoundMetadataValidationError("invalid_request")
    if not 1 <= len(lookups) <= MAX_ROUND_METADATA_LOOKUPS:
        raise RoundMetadataValidationError("invalid_request")
    result = []
    for lookup in lookups:
        if not isinstance(lookup, Mapping):
            raise RoundMetadataValidationError("invalid_request")
        result.append(
            {
                "collection_target": _bounded_string(lookup.get("collection_target"), "collection_target"),
                "publish_timestamp_ms": _timestamp(lookup.get("publish_timestamp_ms")),
            }
        )
    return result


class RedisRoundMetadataStore:
    def __init__(self, redis_client, *, ttl_seconds: int = ROUND_METADATA_TTL_SECONDS) -> None:
        self._redis = redis_client
        self._ttl_seconds = int(ttl_seconds)
        if self._ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")

    async def save(self, envelope: Mapping) -> str:
        normalized = validate_round_metadata_envelope(envelope)
        encoded = canonical_json(normalized)
        key = round_metadata_key(
            normalized["collection_task_id"],
            normalized["collection_target"],
            normalized["publish_timestamp_ms"],
        )
        created = await self._redis.set(key, encoded, ex=self._ttl_seconds, nx=True)
        if created:
            return "created"
        existing = await self._redis.get(key)
        if existing == encoded:
            return "duplicate"
        raise RoundMetadataConflictError()

    async def get_many(self, task_id, lookups: Sequence[Mapping]) -> list[dict]:
        task = _bounded_string(task_id, "collection_task_id")
        normalized_lookups = validate_lookups(lookups)
        keys = [round_metadata_key(task, item["collection_target"], item["publish_timestamp_ms"]) for item in normalized_lookups]
        values = await self._redis.mget(keys)
        result = []
        for lookup, raw in zip(normalized_lookups, values):
            if raw is None:
                raise RoundMetadataMissingError()
            try:
                envelope = validate_round_metadata_envelope(json.loads(raw))
            except (json.JSONDecodeError, RoundMetadataValidationError) as exc:
                raise RoundMetadataError("metadata_unavailable") from exc
            if (
                envelope["collection_task_id"] != task
                or envelope["collection_target"] != lookup["collection_target"]
                or envelope["publish_timestamp_ms"] != lookup["publish_timestamp_ms"]
            ):
                raise RoundMetadataError("metadata_unavailable")
            result.append(envelope)
        if len(canonical_json({"items": result}).encode("utf-8")) > MAX_ROUND_METADATA_RESPONSE_BYTES:
            raise RoundMetadataValidationError("metadata_response_too_large")
        return result
