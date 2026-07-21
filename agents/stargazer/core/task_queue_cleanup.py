from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from arq.constants import (
    default_queue_name,
    in_progress_key_prefix,
    job_key_prefix,
    retry_key_prefix,
)
from redis.exceptions import WatchError

QUEUE_KEY = default_queue_name.encode()
IN_PROGRESS_PREFIX = in_progress_key_prefix.encode()
JOB_PREFIX = job_key_prefix.encode()
RETRY_PREFIX = retry_key_prefix.encode()
RUNNING_PATTERN = b"task:running:*"
DEDUPE_PATTERN = b"task:dedupe:*"


class CleanupStateError(RuntimeError):
    """Redis state is not safe to interpret as a Stargazer task queue."""


class CleanupBackupError(RuntimeError):
    """A recoverable backup could not be created."""


class CleanupDriftError(RuntimeError):
    """Redis state changed after the cleanup plan was built."""


class CleanupExecutionError(RuntimeError):
    """The cleanup transaction failed."""


class CleanupRestoreError(RuntimeError):
    """A cleanup backup could not be restored safely."""


@dataclass(frozen=True)
class CleanupResult:
    deleted_job_count: int
    deleted_marker_count: int
    remaining_queue_jobs: int


@dataclass(frozen=True)
class RestoreResult:
    restored_key_count: int
    restored_queue_job_count: int


@dataclass(frozen=True)
class CleanupPlan:
    all_pending: bool
    include_in_progress: bool
    selected_job_ids: tuple[bytes, ...]
    protected_job_ids: tuple[bytes, ...]
    marker_items: tuple[tuple[bytes, bytes], ...]
    queue_scores: tuple[tuple[bytes, float], ...]
    fingerprint: tuple[tuple[str, str, str], ...]

    @property
    def marker_keys(self) -> tuple[bytes, ...]:
        return tuple(key for key, _job_id in self.marker_items)

    @property
    def target_keys(self) -> tuple[bytes, ...]:
        keys = set(self.marker_keys)
        for job_id in self.selected_job_ids:
            keys.add(JOB_PREFIX + job_id)
            keys.add(RETRY_PREFIX + job_id)
            if self.include_in_progress:
                keys.add(IN_PROGRESS_PREFIX + job_id)
        return tuple(sorted(keys))

    @property
    def watch_keys(self) -> tuple[bytes, ...]:
        keys = {QUEUE_KEY, *self.target_keys}
        for job_id in self.selected_job_ids + self.protected_job_ids:
            keys.add(IN_PROGRESS_PREFIX + job_id)
        return tuple(sorted(keys))


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    return str(value).encode()


def _type_name(redis_client, key: bytes) -> bytes:
    return _as_bytes(redis_client.type(key))


def _read_queue_scores(redis_client) -> dict[bytes, float]:
    queue_type = _type_name(redis_client, QUEUE_KEY)
    if queue_type not in {b"none", b"zset"}:
        actual_type = queue_type.decode(errors="replace")
        raise CleanupStateError(
            f"{default_queue_name} must be a zset, got {actual_type}"
        )
    if queue_type == b"none":
        return {}

    return {
        _as_bytes(job_id): float(score)
        for job_id, score in redis_client.zrange(
            QUEUE_KEY, 0, -1, withscores=True,
        )
    }


def _read_marker_items(redis_client) -> dict[bytes, bytes]:
    marker_items: dict[bytes, bytes] = {}
    for pattern in (RUNNING_PATTERN, DEDUPE_PATTERN):
        for raw_key in redis_client.scan_iter(match=pattern, count=500):
            key = _as_bytes(raw_key)
            marker_type = _type_name(redis_client, key)
            if marker_type != b"string":
                raise CleanupStateError(
                    f"{key.decode(errors='replace')} must be a string, "
                    f"got {marker_type.decode(errors='replace')}"
                )
            job_id = redis_client.get(key)
            if job_id is None:
                raise CleanupStateError(
                    f"{key.decode(errors='replace')} disappeared during scan"
                )
            normalized_job_id = _as_bytes(job_id)
            if not normalized_job_id:
                raise CleanupStateError(
                    f"{key.decode(errors='replace')} contains an empty job id"
                )
            marker_items[key] = normalized_job_id
    return marker_items


def _build_fingerprint(
    redis_client,
    *,
    queue_scores: dict[bytes, float],
    marker_items: dict[bytes, bytes],
    selected_job_ids: set[bytes],
    protected_job_ids: set[bytes],
    in_progress_job_ids: set[bytes],
) -> tuple[tuple[str, str, str], ...]:
    entries: list[tuple[str, str, str]] = []
    relevant_job_ids = selected_job_ids | protected_job_ids
    for job_id in sorted(relevant_job_ids):
        decoded_job_id = job_id.decode(errors="backslashreplace")
        score = queue_scores.get(job_id)
        entries.append(
            (
                "queue",
                decoded_job_id,
                "missing" if score is None else repr(score),
            )
        )
        entries.append(
            (
                "in_progress",
                decoded_job_id,
                "present" if job_id in in_progress_job_ids else "missing",
            )
        )
    for key, job_id in sorted(marker_items.items()):
        if job_id in relevant_job_ids:
            entries.append(
                (
                    "marker",
                    key.decode(errors="backslashreplace"),
                    job_id.decode(errors="backslashreplace"),
                )
            )
    target_keys = set()
    for job_id in selected_job_ids:
        target_keys.add(JOB_PREFIX + job_id)
        target_keys.add(RETRY_PREFIX + job_id)
        target_keys.add(IN_PROGRESS_PREFIX + job_id)
    for key, job_id in marker_items.items():
        if job_id in selected_job_ids:
            target_keys.add(key)
    for key in sorted(target_keys):
        entries.append(
            (
                "type",
                key.decode(errors="backslashreplace"),
                _type_name(redis_client, key).decode(errors="replace"),
            )
        )
    return tuple(entries)


def build_cleanup_plan(
    redis_client, *, all_pending: bool, include_in_progress: bool,
) -> CleanupPlan:
    queue_scores = _read_queue_scores(redis_client)
    marker_items = _read_marker_items(redis_client)

    queue_job_ids = set(queue_scores)
    marker_job_ids = set(marker_items.values())
    related_job_ids = queue_job_ids | marker_job_ids
    in_progress_job_ids = {
        job_id
        for job_id in related_job_ids
        if redis_client.exists(IN_PROGRESS_PREFIX + job_id)
    }

    if all_pending:
        base_candidates = set(queue_job_ids)
    else:
        base_candidates = marker_job_ids & queue_job_ids

    related_in_progress = in_progress_job_ids & related_job_ids
    selected_job_ids = base_candidates - in_progress_job_ids
    if include_in_progress:
        selected_job_ids |= related_in_progress
    protected_job_ids = related_in_progress - selected_job_ids

    selected_marker_items = tuple(
        sorted(
            (key, job_id)
            for key, job_id in marker_items.items()
            if job_id in selected_job_ids
        )
    )
    selected_queue_scores = tuple(
        sorted(
            (job_id, queue_scores[job_id])
            for job_id in selected_job_ids
            if job_id in queue_scores
        )
    )

    return CleanupPlan(
        all_pending=all_pending,
        include_in_progress=include_in_progress,
        selected_job_ids=tuple(sorted(selected_job_ids)),
        protected_job_ids=tuple(sorted(protected_job_ids)),
        marker_items=selected_marker_items,
        queue_scores=selected_queue_scores,
        fingerprint=_build_fingerprint(
            redis_client,
            queue_scores=queue_scores,
            marker_items=marker_items,
            selected_job_ids=selected_job_ids,
            protected_job_ids=protected_job_ids,
            in_progress_job_ids=in_progress_job_ids,
        ),
    )


def _decode_identifier(value: bytes) -> str:
    return value.decode(errors="backslashreplace")


def _backup_payload(redis_client, plan: CleanupPlan, *, redis_db: int) -> dict:
    key_payload = {}
    for key in plan.target_keys:
        dumped = redis_client.dump(key)
        if dumped is None:
            continue
        key_payload[_decode_identifier(key)] = {
            "dump": base64.b64encode(_as_bytes(dumped)).decode(),
            "pttl": int(redis_client.pttl(key)),
            "type": _type_name(redis_client, key).decode(errors="replace"),
        }

    payload = {
        "format_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "redis_db": int(redis_db),
        "mode": "all_pending" if plan.all_pending else "blocking",
        "include_in_progress": plan.include_in_progress,
        "selected_job_ids": [
            _decode_identifier(job_id) for job_id in plan.selected_job_ids
        ],
        "protected_job_ids": [
            _decode_identifier(job_id) for job_id in plan.protected_job_ids
        ],
        "queue_scores": {
            _decode_identifier(job_id): score
            for job_id, score in plan.queue_scores
        },
        "marker_items": {
            _decode_identifier(key): _decode_identifier(job_id)
            for key, job_id in plan.marker_items
        },
        "keys": key_payload,
    }
    payload["content_sha256"] = _payload_digest(payload)
    return payload


def _payload_digest(payload: dict) -> str:
    digest_payload = dict(payload)
    digest_payload.pop("content_sha256", None)
    serialized = json.dumps(
        digest_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


def create_cleanup_backup(
    redis_client, plan: CleanupPlan, *, backup_dir: Path, redis_db: int,
) -> Path:
    backup_path = None
    try:
        backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(backup_dir, 0o700)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = backup_dir / (
            f"stargazer-task-queue-{timestamp}-{secrets.token_hex(4)}.json"
        )
        payload = _backup_payload(redis_client, plan, redis_db=redis_db)
        file_descriptor = os.open(
            backup_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600,
        )
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, sort_keys=True)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.chmod(backup_path, 0o600)
        return backup_path
    except Exception as exc:
        if backup_path is not None:
            try:
                backup_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise CleanupBackupError("failed to create task queue backup") from exc


def backup_and_apply_cleanup(
    redis_client, plan: CleanupPlan, *, backup_dir: Path, redis_db: int,
) -> tuple[Path, CleanupResult]:
    """Back up and delete one stable Redis version under a single WATCH."""
    if not plan.selected_job_ids:
        raise CleanupStateError("cleanup plan has no selected jobs")

    try:
        with redis_client.pipeline() as pipe:
            pipe.watch(*plan.watch_keys)
            try:
                current_plan = build_cleanup_plan(
                    pipe,
                    all_pending=plan.all_pending,
                    include_in_progress=plan.include_in_progress,
                )
                if current_plan != plan:
                    raise CleanupDriftError("cleanup target state changed")
                backup_path = create_cleanup_backup(
                    pipe, plan, backup_dir=backup_dir, redis_db=redis_db,
                )
            except (CleanupStateError, CleanupDriftError) as exc:
                pipe.unwatch()
                raise CleanupDriftError(
                    "cleanup target state changed"
                ) from exc
            except CleanupBackupError:
                pipe.unwatch()
                raise

            pipe.multi()
            pipe.zrem(QUEUE_KEY, *plan.selected_job_ids)
            if plan.target_keys:
                pipe.delete(*plan.target_keys)
            pipe.zcard(QUEUE_KEY)
            transaction_results = pipe.execute()
    except WatchError as exc:
        raise CleanupDriftError("cleanup target state changed") from exc
    except (CleanupBackupError, CleanupDriftError):
        raise
    except Exception as exc:
        raise CleanupExecutionError("cleanup transaction failed") from exc

    return (
        backup_path,
        CleanupResult(
            deleted_job_count=len(plan.selected_job_ids),
            deleted_marker_count=len(plan.marker_items),
            remaining_queue_jobs=int(transaction_results[-1]),
        ),
    )


def _load_restore_payload(
    backup_path: Path, *, redis_db: int
) -> tuple[
    dict[bytes, tuple[int, bytes]], dict[bytes, float], dict[bytes, bytes],
]:
    try:
        payload = json.loads(backup_path.read_text(encoding="utf-8"))
        expected_fields = {
            "content_sha256",
            "created_at",
            "format_version",
            "include_in_progress",
            "keys",
            "marker_items",
            "mode",
            "protected_job_ids",
            "queue_scores",
            "redis_db",
            "selected_job_ids",
        }
        if set(payload) != expected_fields:
            raise ValueError("backup schema does not match")
        if payload.get("format_version") != 1:
            raise ValueError("unsupported backup format")
        if not secrets.compare_digest(
            str(payload["content_sha256"]), _payload_digest(payload)
        ):
            raise ValueError("backup digest does not match")
        if int(payload["redis_db"]) != int(redis_db):
            raise ValueError("backup Redis DB does not match")
        if payload["mode"] not in {"blocking", "all_pending"}:
            raise ValueError("backup mode is invalid")
        if not isinstance(payload["include_in_progress"], bool):
            raise ValueError("backup mode flags are invalid")

        selected_job_values = payload["selected_job_ids"]
        if not isinstance(selected_job_values, list):
            raise ValueError("selected jobs are invalid")
        selected_job_ids = {
            str(job_id).encode() for job_id in selected_job_values
        }
        if (
            not selected_job_ids
            or len(selected_job_ids) != len(selected_job_values)
            or b"" in selected_job_ids
        ):
            raise ValueError("selected jobs are invalid")

        protected_values = payload["protected_job_ids"]
        if not isinstance(protected_values, list):
            raise ValueError("protected jobs are invalid")
        protected_job_ids = {
            str(job_id).encode() for job_id in protected_values
        }
        if protected_job_ids & selected_job_ids:
            raise ValueError("selected and protected jobs overlap")

        if not isinstance(payload["marker_items"], dict):
            raise ValueError("markers are invalid")
        marker_keys = set()
        marker_job_ids = set()
        for raw_key, raw_job_id in payload["marker_items"].items():
            key = str(raw_key).encode()
            job_id = str(raw_job_id).encode()
            valid_prefix = any(
                key.startswith(pattern.removesuffix(b"*"))
                for pattern in (RUNNING_PATTERN, DEDUPE_PATTERN)
            )
            if not valid_prefix or job_id not in selected_job_ids:
                raise ValueError("backup contains an invalid marker")
            marker_keys.add(key)
            marker_job_ids.add(job_id)
        allowed_keys = set(marker_keys)
        for job_id in selected_job_ids:
            allowed_keys.update(
                {
                    JOB_PREFIX + job_id,
                    RETRY_PREFIX + job_id,
                    IN_PROGRESS_PREFIX + job_id,
                }
            )

        restore_keys: dict[bytes, tuple[int, bytes]] = {}
        key_job_ids = set()
        if not isinstance(payload["keys"], dict):
            raise ValueError("backup keys are invalid")
        for raw_key, key_payload in payload["keys"].items():
            key = str(raw_key).encode()
            if key not in allowed_keys:
                raise ValueError("backup contains an unexpected key")
            if not isinstance(key_payload, dict) or set(key_payload) != {
                "dump",
                "pttl",
                "type",
            }:
                raise ValueError("backup key schema is invalid")
            if key_payload["type"] != "string":
                raise ValueError("backup key type is invalid")
            for prefix in (JOB_PREFIX, RETRY_PREFIX, IN_PROGRESS_PREFIX):
                if key.startswith(prefix):
                    job_id = key.removeprefix(prefix)
                    if job_id not in selected_job_ids:
                        raise ValueError("backup key job is invalid")
                    if (
                        prefix == IN_PROGRESS_PREFIX
                        and not payload["include_in_progress"]
                    ):
                        raise ValueError("unexpected in-progress key")
                    key_job_ids.add(job_id)
                    break
            pttl = int(key_payload["pttl"])
            if pttl < -1:
                raise ValueError("backup contains an invalid TTL")
            ttl = 0 if pttl == -1 else max(1, pttl)
            dumped = base64.b64decode(key_payload["dump"], validate=True)
            restore_keys[key] = (ttl, dumped)

        queue_scores: dict[bytes, float] = {}
        if not isinstance(payload["queue_scores"], dict):
            raise ValueError("queue scores are invalid")
        for raw_job_id, raw_score in payload["queue_scores"].items():
            job_id = str(raw_job_id).encode()
            score = float(raw_score)
            if job_id not in selected_job_ids or not math.isfinite(score):
                raise ValueError("backup contains an invalid queue member")
            queue_scores[job_id] = score
        if not marker_keys <= set(restore_keys):
            raise ValueError("backup is missing marker data")
        artifact_job_ids = marker_job_ids | key_job_ids | set(queue_scores)
        if artifact_job_ids != selected_job_ids:
            raise ValueError("backup selected jobs do not match artifacts")
        if not restore_keys and not queue_scores:
            raise ValueError("backup contains no restorable data")
    except Exception as exc:
        raise CleanupRestoreError("invalid task queue backup") from exc

    marker_items = {
        str(key).encode(): str(job_id).encode()
        for key, job_id in payload["marker_items"].items()
    }
    return restore_keys, queue_scores, marker_items


def restore_cleanup_backup(
    redis_client, *, backup_path: Path, redis_db: int,
) -> RestoreResult:
    """Restore one cleanup backup without overwriting current Redis state."""
    restore_keys, queue_scores, marker_items = _load_restore_payload(
        backup_path, redis_db=redis_db
    )
    token = secrets.token_hex(12).encode()
    temporary_keys = {
        key: b"stargazer:task-queue-restore:tmp:"
        + token
        + b":"
        + str(index).encode()
        for index, key in enumerate(sorted(restore_keys))
    }
    watch_keys = tuple(
        sorted({QUEUE_KEY, *restore_keys, *temporary_keys.values()})
    )

    try:
        for key, (ttl, dumped) in sorted(restore_keys.items()):
            temporary_key = temporary_keys[key]
            redis_client.restore(temporary_key, ttl, dumped, replace=False)
            if _type_name(redis_client, temporary_key) != b"string":
                raise CleanupRestoreError("backup key type is invalid")
            if (
                key in marker_items
                and redis_client.get(temporary_key) != marker_items[key]
            ):
                raise CleanupRestoreError("backup marker value is invalid")

        with redis_client.pipeline() as pipe:
            pipe.watch(*watch_keys)
            queue_type = _type_name(pipe, QUEUE_KEY)
            if queue_type not in {b"none", b"zset"}:
                raise CleanupRestoreError("queue is not restorable")
            if any(pipe.exists(key) for key in restore_keys):
                raise CleanupRestoreError("restore target already exists")
            if any(
                pipe.zscore(QUEUE_KEY, job_id) is not None
                for job_id in queue_scores
            ):
                raise CleanupRestoreError("queue member already exists")
            if any(
                not pipe.exists(temporary_key)
                for temporary_key in temporary_keys.values()
            ):
                raise CleanupRestoreError("validated restore data expired")

            pipe.multi()
            for key, temporary_key in sorted(temporary_keys.items()):
                pipe.renamenx(temporary_key, key)
            if queue_scores:
                pipe.zadd(QUEUE_KEY, queue_scores)
            transaction_results = pipe.execute()
            rename_results = transaction_results[: len(temporary_keys)]
            if not all(rename_results):
                raise CleanupRestoreError("restore publish was incomplete")
    except WatchError as exc:
        raise CleanupRestoreError("restore target state changed") from exc
    except CleanupRestoreError:
        raise
    except Exception as exc:
        raise CleanupRestoreError("task queue restore failed") from exc
    finally:
        if temporary_keys:
            try:
                redis_client.delete(*temporary_keys.values())
            except Exception:
                pass

    return RestoreResult(
        restored_key_count=len(restore_keys),
        restored_queue_job_count=len(queue_scores),
    )


def apply_cleanup_plan(redis_client, plan: CleanupPlan) -> CleanupResult:
    if not plan.selected_job_ids:
        return CleanupResult(
            deleted_job_count=0,
            deleted_marker_count=0,
            remaining_queue_jobs=int(redis_client.zcard(QUEUE_KEY)),
        )

    try:
        with redis_client.pipeline() as pipe:
            pipe.watch(*plan.watch_keys)
            try:
                current_plan = build_cleanup_plan(
                    pipe,
                    all_pending=plan.all_pending,
                    include_in_progress=plan.include_in_progress,
                )
            except CleanupStateError as exc:
                pipe.unwatch()
                raise CleanupDriftError(
                    "cleanup target state changed"
                ) from exc

            if current_plan != plan:
                pipe.unwatch()
                raise CleanupDriftError("cleanup target state changed")

            pipe.multi()
            pipe.zrem(QUEUE_KEY, *plan.selected_job_ids)
            if plan.target_keys:
                pipe.delete(*plan.target_keys)
            pipe.zcard(QUEUE_KEY)
            transaction_results = pipe.execute()
    except WatchError as exc:
        raise CleanupDriftError("cleanup target state changed") from exc
    except CleanupDriftError:
        raise
    except Exception as exc:
        raise CleanupExecutionError("cleanup transaction failed") from exc

    return CleanupResult(
        deleted_job_count=len(plan.selected_job_ids),
        deleted_marker_count=len(plan.marker_items),
        remaining_queue_jobs=int(transaction_results[-1]),
    )
