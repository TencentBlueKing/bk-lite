from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import requests

from apps.apm.adapters.victoriametrics import TelemetryStoreUnavailable
from apps.apm.services.contracts import (
    SpanDetail,
    TraceDetail,
    TracePage,
    TraceSearchQuery,
    TraceSummary,
)
from apps.apm.services.identity import normalize_identity

_RAW_SPAN_PARSE_LIMIT = 1001


def _tag_map(tags: object) -> dict[str, object]:
    if not isinstance(tags, list):
        return {}
    result: dict[str, object] = {}
    for tag in tags:
        if isinstance(tag, dict) and isinstance(tag.get("key"), str):
            result[tag["key"]] = tag.get("value")
    return result


def _status_from_tags(tags: dict[str, object]) -> str:
    value = str(tags.get("otel.status_code", tags.get("status.code", ""))).casefold()
    error_tag = tags.get("error")
    if value in {"error", "status_code_error", "2"} or error_tag is True or str(error_tag).casefold() in {"1", "true"}:
        return "error"
    return "ok"


def _source_id(attributes: dict[str, object]) -> UUID | None:
    try:
        return UUID(str(attributes.get("bk.ingest_source.id", "")))
    except (TypeError, ValueError):
        return None


def _encode_cursor(started_at: datetime) -> str:
    microseconds = int(started_at.timestamp() * 1_000_000) - 1
    return base64.urlsafe_b64encode(str(microseconds).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> datetime:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        microseconds = int(base64.urlsafe_b64decode(padded.encode()).decode())
        return datetime.fromtimestamp(microseconds / 1_000_000, tz=UTC)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Trace 游标无效") from exc


class VictoriaTracesTraceStore:
    """通过受控 Jaeger JSON 查询隐藏 VictoriaTraces 的查询和响应格式。"""

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        session: requests.Session | None = None,
    ):
        self.endpoint = (endpoint or os.getenv("APM_VICTORIATRACES_QUERY_ENDPOINT") or "http://127.0.0.1:10428").rstrip("/")
        self.session = session or requests.Session()
        self.timeout = (3, int(os.getenv("APM_VICTORIATRACES_QUERY_TIMEOUT", "15")))
        self.verify = os.getenv("APM_VICTORIATRACES_VERIFY_TLS", "true").casefold() != "false"
        user = os.getenv("APM_VICTORIATRACES_USER")
        password = os.getenv("APM_VICTORIATRACES_PASSWORD")
        self.auth = (user, password or "") if user else None

    def search(self, query: TraceSearchQuery) -> TracePage:
        ended_at = min(query.ended_at, _decode_cursor(query.cursor)) if query.cursor else query.ended_at
        tags: dict[str, str] = {
            "resource_attr:deployment.environment": query.environment or "",
        }
        if query.service_namespace is not None:
            tags["resource_attr:service.namespace"] = query.service_namespace
        if query.instance_id is not None:
            tags["resource_attr:service.instance.id"] = query.instance_id

        payload = self._request_json(
            "/select/jaeger/api/traces",
            params={
                "service": query.service_name,
                "tags": json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
                "start": int(query.started_at.timestamp() * 1_000_000),
                "end": int(ended_at.timestamp() * 1_000_000),
                "limit": query.limit + 1,
            },
        )
        raw_traces = payload.get("data", [])
        if not isinstance(raw_traces, list):
            raise TelemetryStoreUnavailable("VictoriaTraces 返回了无效的搜索结果")

        summaries: list[TraceSummary] = []
        for raw_trace in raw_traces:
            detail = self._parse_trace(raw_trace)
            if detail is None:
                continue
            matching_span = self._matching_span(detail, query)
            if matching_span is None:
                continue
            summaries.append(self._summary(detail, matching_span))
        summaries.sort(key=lambda item: (item.started_at, item.trace_id), reverse=True)

        page_items = tuple(summaries[: query.limit])
        next_cursor = _encode_cursor(page_items[-1].started_at) if len(summaries) > query.limit and page_items else None
        return TracePage(items=page_items, next_cursor=next_cursor)

    def get_trace(self, trace_id: str) -> TraceDetail | None:
        payload = self._request_json(f"/select/jaeger/api/traces/{trace_id}", allow_not_found=True)
        if payload is None:
            return None
        raw_traces = payload.get("data", [])
        if not isinstance(raw_traces, list) or not raw_traces:
            return None
        return self._parse_trace(raw_traces[0])

    def _request_json(
        self,
        path: str,
        *,
        params: dict[str, object] | None = None,
        allow_not_found: bool = False,
    ) -> dict[str, Any] | None:
        try:
            response = self.session.get(
                f"{self.endpoint}{path}",
                params=params,
                timeout=self.timeout,
                verify=self.verify,
                auth=self.auth,
                headers={"Accept": "application/json"},
            )
            if allow_not_found and response.status_code == 404:
                return None
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise TelemetryStoreUnavailable("VictoriaTraces 查询不可用") from exc
        if not isinstance(payload, dict):
            raise TelemetryStoreUnavailable("VictoriaTraces 返回了无效响应")
        return payload

    def _parse_trace(self, raw_trace: object) -> TraceDetail | None:
        if not isinstance(raw_trace, dict):
            return None
        trace_id = str(raw_trace.get("traceID", ""))
        raw_spans = raw_trace.get("spans", [])
        processes = raw_trace.get("processes", {})
        if not trace_id or not isinstance(raw_spans, list) or not isinstance(processes, dict):
            return None

        spans: list[SpanDetail] = []
        for raw_span in raw_spans[:_RAW_SPAN_PARSE_LIMIT]:
            if not isinstance(raw_span, dict):
                continue
            process = processes.get(raw_span.get("processID"), {})
            process = process if isinstance(process, dict) else {}
            resource_attributes = _tag_map(process.get("tags"))
            service_name = str(process.get("serviceName") or resource_attributes.get("service.name") or "")
            attributes = {**resource_attributes, **_tag_map(raw_span.get("tags"))}
            started_at = datetime.fromtimestamp(float(raw_span.get("startTime", 0)) / 1_000_000, tz=UTC)
            references = raw_span.get("references", [])
            parent_span_id = None
            if isinstance(references, list):
                parent = next(
                    (item for item in references if isinstance(item, dict) and str(item.get("refType", "")).upper() == "CHILD_OF"),
                    None,
                )
                if parent is not None:
                    parent_span_id = str(parent.get("spanID") or "") or None
            spans.append(
                SpanDetail(
                    span_id=str(raw_span.get("spanID", "")),
                    parent_span_id=parent_span_id,
                    name=str(raw_span.get("operationName", "")),
                    started_at=started_at,
                    duration_ms=float(raw_span.get("duration", 0)) / 1000,
                    status=_status_from_tags(attributes),
                    attributes=attributes,
                    service_namespace=str(resource_attributes.get("service.namespace", "")),
                    service_name=service_name,
                    environment=str(
                        resource_attributes.get(
                            "deployment.environment",
                            resource_attributes.get("deployment.environment.name", ""),
                        )
                    ),
                    instance_id=str(resource_attributes.get("service.instance.id") or "") or None,
                    kind=str(attributes.get("span.kind", "unspecified")).removeprefix("SPAN_KIND_").casefold(),
                    ingest_source_id=_source_id(resource_attributes),
                )
            )
        if not spans:
            return None
        spans.sort(key=lambda item: (item.started_at, item.span_id))
        root = next((item for item in spans if item.parent_span_id is None), spans[0])
        root_attributes = dict(root.attributes)
        return TraceDetail(
            trace_id=trace_id,
            spans=tuple(spans),
            service_namespace=root.service_namespace,
            service_name=root.service_name,
            environment=root.environment,
            instance_id=root.instance_id,
            ingest_source_id=_source_id(root_attributes),
            truncated=len(raw_spans) > _RAW_SPAN_PARSE_LIMIT,
        )

    @staticmethod
    def _matching_span(detail: TraceDetail, query: TraceSearchQuery) -> SpanDetail | None:
        for span in detail.spans:
            if normalize_identity(span.service_name) != normalize_identity(query.service_name or ""):
                continue
            if query.service_namespace is not None and normalize_identity(span.service_namespace) != normalize_identity(query.service_namespace):
                continue
            if span.environment != query.environment:
                continue
            if query.instance_id is not None and span.instance_id != query.instance_id:
                continue
            return span
        return None

    @staticmethod
    def _summary(detail: TraceDetail, matching_span: SpanDetail) -> TraceSummary:
        started_at = min(span.started_at for span in detail.spans)
        ended_at = max(span.started_at + timedelta(milliseconds=span.duration_ms) for span in detail.spans)
        root = next((span for span in detail.spans if span.parent_span_id is None), detail.spans[0])
        return TraceSummary(
            trace_id=detail.trace_id,
            started_at=started_at,
            duration_ms=max(0, (ended_at - started_at).total_seconds() * 1000),
            service_namespace=matching_span.service_namespace,
            service_name=matching_span.service_name,
            environment=matching_span.environment,
            instance_id=matching_span.instance_id,
            status="error" if any(span.status == "error" for span in detail.spans) else "ok",
            root_span_name=root.name,
            span_count=len(detail.spans),
            ingest_source_id=_source_id(dict(matching_span.attributes)),
        )
