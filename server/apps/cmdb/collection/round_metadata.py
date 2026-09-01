"""从目标区域 Stargazer 精确读取配置快照轮次元数据。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from apps.rpc.stargazer import Stargazer

ROUND_METADATA_SCHEMA_VERSION = 1
ROUND_METADATA_KIND = "inventory_snapshot"
ROUND_METADATA_BATCH_SIZE = 50
ROUND_METADATA_TIMEOUT_SECONDS = 3
MAX_IDENTITY_LENGTH = 512


class RoundMetadataProtocolError(RuntimeError):
    """元数据缺失或不可信；调用方必须在图写入前终止本轮。"""


def _bounded_string(value, field: str) -> str:
    result = str(value or "").strip()
    if not result or len(result) > MAX_IDENTITY_LENGTH:
        raise RoundMetadataProtocolError(f"invalid_{field}")
    return result


def _timestamp_ms(value) -> int:
    if isinstance(value, bool):
        raise RoundMetadataProtocolError("invalid_publish_timestamp")
    try:
        result = int(round(float(value) * 1000))
    except (TypeError, ValueError, OSError) as exc:
        raise RoundMetadataProtocolError("invalid_publish_timestamp") from exc
    if result <= 0:
        raise RoundMetadataProtocolError("invalid_publish_timestamp")
    return result


def resolve_stargazer_namespace(task) -> str:
    access_point = getattr(task, "access_point", None)
    if isinstance(access_point, list) and access_point:
        access_point = access_point[0]
    if not isinstance(access_point, Mapping):
        access_point = {}
    cloud_name = str(access_point.get("cloud_name") or access_point.get("cloud_region_name") or "default").strip()
    return f"{cloud_name or 'default'}_stargazer"


def build_round_metadata_lookups(rows: Sequence[Mapping]) -> list[dict]:
    result = []
    seen = set()
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        target = _bounded_string(row.get("collection_target"), "collection_target")
        timestamp_ms = _timestamp_ms(row.get("_metric_time"))
        identity = (target, timestamp_ms)
        if identity in seen:
            continue
        seen.add(identity)
        result.append({"collection_target": target, "publish_timestamp_ms": timestamp_ms})
    if not result:
        raise RoundMetadataProtocolError("metadata_lookup_empty")
    return result


class RoundMetadataReader:
    def __init__(self, task, *, rpc_factory=Stargazer) -> None:
        self._task = task
        self._task_id = str(getattr(task, "id", "") or "").strip()
        if not self._task_id:
            raise RoundMetadataProtocolError("invalid_collection_task_id")
        self._client = rpc_factory(instance_id=resolve_stargazer_namespace(task))

    def get_many(self, lookups: Sequence[Mapping], *, model_id: str) -> dict[tuple[str, int], dict]:
        normalized = self._normalize_lookups(lookups)
        result = {}
        for offset in range(0, len(normalized), ROUND_METADATA_BATCH_SIZE):
            batch = normalized[offset : offset + ROUND_METADATA_BATCH_SIZE]
            payload = {
                "schema_version": ROUND_METADATA_SCHEMA_VERSION,
                "collection_task_id": self._task_id,
                "instance_id": f"cmdb_{self._task_id}",
                "lookups": batch,
            }
            try:
                response = self._client.get_collection_round_metadata(
                    payload,
                    timeout=ROUND_METADATA_TIMEOUT_SECONDS,
                )
            except Exception as exc:  # noqa: BLE001 - 跨服务错误统一收口为 fail-closed 协议错误
                raise RoundMetadataProtocolError("metadata_unavailable") from exc
            result.update(self._validate_response(response, batch, model_id=model_id))
        if len(result) != len(normalized):
            raise RoundMetadataProtocolError("metadata_missing")
        return result

    @staticmethod
    def _normalize_lookups(lookups: Sequence[Mapping]) -> list[dict]:
        if isinstance(lookups, (str, bytes)) or not isinstance(lookups, Sequence) or not lookups:
            raise RoundMetadataProtocolError("metadata_lookup_empty")
        result = []
        seen = set()
        for item in lookups:
            if not isinstance(item, Mapping):
                raise RoundMetadataProtocolError("invalid_lookup")
            target = _bounded_string(item.get("collection_target"), "collection_target")
            timestamp = item.get("publish_timestamp_ms")
            if isinstance(timestamp, bool):
                raise RoundMetadataProtocolError("invalid_publish_timestamp")
            try:
                timestamp = int(timestamp)
            except (TypeError, ValueError) as exc:
                raise RoundMetadataProtocolError("invalid_publish_timestamp") from exc
            if timestamp <= 0:
                raise RoundMetadataProtocolError("invalid_publish_timestamp")
            identity = (target, timestamp)
            if identity in seen:
                continue
            seen.add(identity)
            result.append({"collection_target": target, "publish_timestamp_ms": timestamp})
        return result

    def _validate_response(self, response, requested, *, model_id: str) -> dict[tuple[str, int], dict]:
        if not isinstance(response, Mapping) or response.get("success") is not True:
            raise RoundMetadataProtocolError("metadata_unavailable")
        if response.get("schema_version") != ROUND_METADATA_SCHEMA_VERSION or not isinstance(response.get("items"), list):
            raise RoundMetadataProtocolError("unsupported_metadata_schema")
        requested_keys = {(item["collection_target"], item["publish_timestamp_ms"]) for item in requested}
        result = {}
        for item in response["items"]:
            normalized = self._validate_envelope(item, model_id=model_id)
            key = (normalized["collection_target"], normalized["publish_timestamp_ms"])
            if key not in requested_keys or key in result:
                raise RoundMetadataProtocolError("metadata_identity_mismatch")
            result[key] = normalized
        if set(result) != requested_keys:
            raise RoundMetadataProtocolError("metadata_missing")
        return result

    def _validate_envelope(self, item, *, model_id: str) -> dict:
        if not isinstance(item, Mapping):
            raise RoundMetadataProtocolError("invalid_metadata")
        if item.get("schema_version") != ROUND_METADATA_SCHEMA_VERSION or item.get("kind") != ROUND_METADATA_KIND:
            raise RoundMetadataProtocolError("unsupported_metadata_schema")
        task_id = _bounded_string(item.get("collection_task_id"), "collection_task_id")
        if task_id != self._task_id or item.get("instance_id") != f"cmdb_{self._task_id}":
            raise RoundMetadataProtocolError("metadata_identity_mismatch")
        if item.get("model_id") != model_id:
            raise RoundMetadataProtocolError("metadata_model_mismatch")
        status = item.get("snapshot_status")
        if status not in {"complete", "partial"}:
            raise RoundMetadataProtocolError("invalid_snapshot_status")
        details = item.get("details")
        if not isinstance(details, Mapping):
            raise RoundMetadataProtocolError("invalid_metadata_details")
        normalized = dict(item)
        normalized["collection_target"] = _bounded_string(item.get("collection_target"), "collection_target")
        try:
            normalized["publish_timestamp_ms"] = int(item.get("publish_timestamp_ms"))
        except (TypeError, ValueError) as exc:
            raise RoundMetadataProtocolError("invalid_publish_timestamp") from exc
        _bounded_string(item.get("snapshot_id"), "snapshot_id")
        return normalized
