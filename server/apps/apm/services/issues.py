from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from apps.apm.services.contracts import (
    IssueDistribution,
    IssuePage,
    IssueProjection,
    IssueSampleTrace,
    SpanDetail,
    SpanSummary,
    TraceDetail,
)
from apps.apm.services.query import DjangoTelemetryQueryService

MAX_SAMPLE_TRACES = 5
_UNATTRIBUTED_MESSAGE = "OTel Span status=Error"
_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", re.IGNORECASE)
_HEX_RE = re.compile(r"\b(?:0x)?[0-9a-f]{12,}\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


@dataclass(frozen=True)
class _IssueOccurrence:
    summary: SpanSummary
    exception_type: str
    message: str
    stacktrace: str
    key_frame: str
    version: str


def _text(attributes: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = attributes.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _message_skeleton(message: str) -> str:
    normalized = _UUID_RE.sub("<uuid>", message.casefold())
    normalized = _HEX_RE.sub("<id>", normalized)
    normalized = _NUMBER_RE.sub("<n>", normalized)
    return " ".join(normalized.split())


def _key_frame(stacktrace: str) -> str:
    lines = [line.strip() for line in stacktrace.splitlines() if line.strip()]
    return next((line for line in lines[1:] if " at " in f" {line} "), lines[-1] if lines else "")


def _fingerprint(occurrence: _IssueOccurrence) -> str:
    identity = (
        occurrence.summary.service_namespace,
        occurrence.summary.service_name,
        occurrence.exception_type.casefold(),
        _message_skeleton(occurrence.message),
        occurrence.key_frame.casefold(),
    )
    return hashlib.sha256("\0".join(identity).encode("utf-8")).hexdigest()[:32]


def _distribution(values: Iterable[str], total: int) -> tuple[IssueDistribution, ...]:
    counts = Counter(value or "(未设置)" for value in values)
    return tuple(
        IssueDistribution(value=value, count=count, percent=round(count / total * 100, 2))
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


class DjangoTelemetryIssueService:
    """把组织可见的真实 Error Span 投影为有界、只读 Issue；不伪装持久化生命周期。"""

    def __init__(self, query_service: DjangoTelemetryQueryService):
        self.query_service = query_service

    def project(self, summaries: Iterable[SpanSummary], *, next_cursor: str | None) -> IssuePage:
        occurrences: list[_IssueOccurrence] = []
        details: dict[str, TraceDetail | None] = {}
        for summary in summaries:
            if summary.trace_id not in details:
                details[summary.trace_id] = self.query_service.get_trace(summary.trace_id)
            detail = details[summary.trace_id]
            span = next((item for item in detail.spans if item.span_id == summary.span_id), None) if detail is not None else None
            occurrences.append(self._occurrence(summary, span))

        groups: dict[str, list[_IssueOccurrence]] = {}
        for occurrence in occurrences:
            groups.setdefault(_fingerprint(occurrence), []).append(occurrence)

        issues = tuple(
            self._projection(fingerprint, group)
            for fingerprint, group in sorted(
                groups.items(),
                key=lambda item: (-len(item[1]), -max(value.summary.started_at.timestamp() for value in item[1]), item[0]),
            )
        )
        return IssuePage(items=issues, next_cursor=next_cursor, truncated=next_cursor is not None)

    @staticmethod
    def _occurrence(summary: SpanSummary, span: SpanDetail | None) -> _IssueOccurrence:
        attributes = dict(span.attributes) if span is not None else {}
        exception_type = (
            _text(
                attributes,
                "exception.type",
                "event_attr:exception.type",
                "span_attr:exception.type",
            )
            or "SpanError"
        )
        message = (
            _text(
                attributes,
                "exception.message",
                "event_attr:exception.message",
                "span_attr:exception.message",
                "otel.status_description",
                "status.message",
            )
            or _UNATTRIBUTED_MESSAGE
        )
        stacktrace = _text(
            attributes,
            "exception.stacktrace",
            "event_attr:exception.stacktrace",
            "span_attr:exception.stacktrace",
        )
        return _IssueOccurrence(
            summary=summary,
            exception_type=exception_type,
            message=message,
            stacktrace=stacktrace,
            key_frame=_key_frame(stacktrace),
            version=_text(attributes, "service.version", "resource_attr:service.version"),
        )

    @staticmethod
    def _projection(fingerprint: str, occurrences: list[_IssueOccurrence]) -> IssueProjection:
        sorted_items = sorted(occurrences, key=lambda item: (item.summary.started_at, item.summary.span_id), reverse=True)
        representative = sorted_items[0]
        trace_ids = {item.summary.trace_id for item in sorted_items}
        total = len(sorted_items)
        samples = tuple(
            IssueSampleTrace(
                trace_id=item.summary.trace_id,
                span_id=item.summary.span_id,
                endpoint=item.summary.name,
                started_at=item.summary.started_at,
                duration_ms=item.summary.duration_ms,
            )
            for item in sorted_items[:MAX_SAMPLE_TRACES]
        )
        return IssueProjection(
            fingerprint=fingerprint,
            exception_type=representative.exception_type,
            message=representative.message,
            stacktrace=representative.stacktrace,
            service_namespace=representative.summary.service_namespace,
            service_name=representative.summary.service_name,
            environment=representative.summary.environment,
            occurrences=total,
            affected_traces=len(trace_ids),
            last_seen_at=representative.summary.started_at,
            version_distribution=_distribution((item.version for item in sorted_items), total),
            endpoint_distribution=_distribution((item.summary.name for item in sorted_items), total),
            sample_traces=samples,
        )
