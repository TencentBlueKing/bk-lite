from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from apps.apm.services.contracts import ServiceErrorSampleTrace, ServiceErrorType, ServiceFailedEndpoint

UNATTRIBUTED_ERROR_TYPE = "未携带错误信息"
MAX_FAILED_ENDPOINTS = 10
MAX_ERROR_TYPES = 10
MAX_ERROR_TYPE_GROUPS = 200
MAX_ERROR_TYPE_SAMPLES = 3
_ENTRY_KINDS = frozenset({"server", "consumer", "2", "5"})
_DOWNSTREAM_KINDS = frozenset({"client", "producer", "3", "4"})


@dataclass(frozen=True)
class RawErrorGroup:
    kind: str
    exception_type: str
    span_error_type: str
    status_message: str
    http_status: str
    exception_message: str
    count: int
    last_seen_at: datetime


def coalesce_error_type(
    *,
    exception_type: str = "",
    span_error_type: str = "",
    status_message: str = "",
    http_status: str = "",
) -> str:
    if exception_type:
        return exception_type
    if span_error_type:
        return span_error_type
    if status_message:
        return status_message
    if http_status.startswith("5"):
        return f"HTTP {http_status}"
    return UNATTRIBUTED_ERROR_TYPE


def coalesce_error_message(
    *,
    exception_message: str = "",
    status_message: str = "",
    error_type: str,
) -> str:
    if exception_message:
        return exception_message
    if status_message and status_message != error_type:
        return status_message
    return ""


def location_from_kind(kind: str) -> str:
    code = kind.strip().casefold()
    if code in _ENTRY_KINDS:
        return "entry"
    if code in _DOWNSTREAM_KINDS:
        return "downstream"
    return "internal"


def rank_failed_endpoints(
    items: Sequence[tuple[str, int, int]],
    *,
    total_errors: int,
    limit: int = MAX_FAILED_ENDPOINTS,
) -> tuple[tuple[ServiceFailedEndpoint, ...], int]:
    ranked = sorted(
        ((endpoint, requests, errors) for endpoint, requests, errors in items if errors > 0),
        key=lambda item: (-item[2], item[0]),
    )
    top = ranked[:limit]
    other = max(0, total_errors - sum(item[2] for item in top))
    endpoints = tuple(
        ServiceFailedEndpoint(
            endpoint=endpoint,
            error_count=errors,
            request_count=requests,
            error_rate=(errors / requests) if requests else None,
        )
        for endpoint, requests, errors in top
    )
    return endpoints, other


def merge_error_groups(
    groups: Sequence[RawErrorGroup],
    *,
    limit: int = MAX_ERROR_TYPES,
) -> tuple[ServiceErrorType, ...]:
    merged: dict[str, list[RawErrorGroup]] = defaultdict(list)
    for group in groups:
        if group.count <= 0:
            continue
        error_type = coalesce_error_type(
            exception_type=group.exception_type,
            span_error_type=group.span_error_type,
            status_message=group.status_message,
            http_status=group.http_status,
        )
        merged[error_type].append(group)
    projections: list[ServiceErrorType] = []
    for error_type, items in merged.items():
        count = sum(item.count for item in items)
        location_counts: dict[str, int] = defaultdict(int)
        for item in items:
            location_counts[location_from_kind(item.kind)] += item.count
        location = max(location_counts, key=lambda key: (location_counts[key], -_location_rank(key)))
        representative = max(
            items,
            key=lambda item: (
                1 if item.exception_message else 0,
                1 if item.exception_type else 0,
                item.count,
                item.last_seen_at,
            ),
        )
        projections.append(
            ServiceErrorType(
                error_type=error_type,
                message=coalesce_error_message(
                    exception_message=representative.exception_message,
                    status_message=representative.status_message,
                    error_type=error_type,
                ),
                count=count,
                location=location,
                last_seen_at=max(item.last_seen_at for item in items),
            )
        )
    projections.sort(key=lambda item: (-item.count, -item.last_seen_at.timestamp(), item.error_type))
    return tuple(projections[:limit])


def attach_samples(
    error_type: ServiceErrorType,
    samples: Sequence[ServiceErrorSampleTrace],
) -> ServiceErrorType:
    return replace(error_type, sample_traces=tuple(samples[:MAX_ERROR_TYPE_SAMPLES]))


def _location_rank(location: str) -> int:
    return {"entry": 0, "downstream": 1, "internal": 2}.get(location, 3)
