from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arq.constants import (
    default_queue_name,
    in_progress_key_prefix,
    job_key_prefix,
    retry_key_prefix,
)


QUEUE_KEY = default_queue_name.encode()
IN_PROGRESS_PREFIX = in_progress_key_prefix.encode()
JOB_PREFIX = job_key_prefix.encode()
RETRY_PREFIX = retry_key_prefix.encode()
RUNNING_PATTERN = b"task:running:*"
DEDUPE_PATTERN = b"task:dedupe:*"


class CleanupStateError(RuntimeError):
    """Redis state is not safe to interpret as a Stargazer task queue."""


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
        raise CleanupStateError(
            f"{default_queue_name} must be a zset, got {queue_type.decode(errors='replace')}"
        )
    if queue_type == b"none":
        return {}

    return {
        _as_bytes(job_id): float(score)
        for job_id, score in redis_client.zrange(
            QUEUE_KEY,
            0,
            -1,
            withscores=True,
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
        entries.append(("queue", decoded_job_id, "missing" if score is None else repr(score)))
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
    return tuple(entries)


def build_cleanup_plan(
    redis_client,
    *,
    all_pending: bool,
    include_in_progress: bool,
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
            queue_scores=queue_scores,
            marker_items=marker_items,
            selected_job_ids=selected_job_ids,
            protected_job_ids=protected_job_ids,
            in_progress_job_ids=in_progress_job_ids,
        ),
    )
